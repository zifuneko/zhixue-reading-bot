# -*- coding: utf-8 -*-
"""
智学网学生端「文章朗读」自动完成脚本

链路：
  edge-tts 合成中文语音
      -> sounddevice 播放到 VB-CABLE 的 CABLE Input（WASAPI）
      -> 安卓模拟器麦克风指向 CABLE Output
      -> App 内录音 -> 停止 -> 点“确定”进入下一段 -> …… -> 交卷页

用法：
  python check_env.py                        # 先做环境自检
  python auto_read.py --mode one             # 只录当前这一段，不提交
  python auto_read.py --mode full            # 从当前段录到最后，停在交卷页
  python auto_read.py --mode full --submit   # 录完并自动点“提交作业”

注意：App 的 resource-id 会随版本变化，换版本后请先跑 --mode one 验证。
"""
import argparse
import asyncio
import os
import re
import sys
import time
import xml.etree.ElementTree as ET

import numpy as np
import sounddevice as sd
import soundfile as sf
import scipy.signal as ss
import uiautomator2 as u2
import edge_tts

PKG = 'com.iflytek.elpmobile.student'
DEFAULT_SERIAL = '127.0.0.1:16416'
OUT_SR = 48000

BASE = os.path.dirname(os.path.abspath(__file__))
SHOT_DIR = os.path.join(BASE, 'shots')
TMP_MP3 = os.path.join(BASE, 'tmp_seg.mp3')

# 常用中文音色
VOICES = {
    '男声-云健（默认）': 'zh-CN-YunjianNeural',
    '男声-云希': 'zh-CN-YunxiNeural',
    '男声-云扬': 'zh-CN-YunyangNeural',
    '女声-晓晓': 'zh-CN-XiaoxiaoNeural',
    '女声-晓伊': 'zh-CN-XiaoyiNeural',
}


def rid(name):
    return '%s:id/%s' % (PKG, name)


def resolve_output_device(hint='CABLE Input'):
    """在声卡列表里挑一个最匹配的播放设备（优先 WASAPI 的 CABLE Input）。"""
    hostapis = [h['name'] for h in sd.query_hostapis()]
    best = None
    for i, dev in enumerate(sd.query_devices()):
        if dev['max_output_channels'] <= 0:
            continue
        name = dev['name']
        if hint.lower() not in name.lower():
            continue
        score = 0
        if 'cable input' in name.lower():
            score += 50
        if 'wasapi' in hostapis[dev['hostapi']].lower():
            score += 20
        if best is None or score > best[0]:
            best = (score, i, name, hostapis[dev['hostapi']])
    if best is None:
        sys.exit(
            '[错误] 没找到包含 "%s" 的播放设备。\n'
            '  · 确认已安装 VB-CABLE 并重启过电脑；\n'
            '  · 或在 Windows 声音设置里检查该设备是否被禁用；\n'
            '  · 也可用 --device 参数手动指定设备编号（python -m sounddevice 可列出）。' % hint
        )
    print('[audio] 输出设备 #%d %s (%s)' % (best[1], best[2], best[3]), flush=True)
    return best[1]


def parse_page(xml):
    """从界面 XML 解析出 (当前段号, 总段数, 当前段文本)。

    当前段文本取自录音卡片（ll_main）内部的 text_content，
    而不是页面上其他位置的同名文本——这一点决定了朗读内容对不对。
    """
    root = ET.fromstring(xml)
    parent = {c: p for p in root.iter() for c in p}

    idx_node = None
    for node in root.iter('node'):
        if node.get('resource-id', '').endswith(':id/text_index'):
            idx_node = node
            break

    n = total = None
    current = ''
    if idx_node is not None:
        m = re.search(r'(\d+)\s*/\s*(\d+)\s*段', idx_node.get('text', ''))
        if m:
            n, total = int(m.group(1)), int(m.group(2))

        # 向上找到所属卡片容器 ll_main
        card = idx_node
        while card in parent:
            card = parent[card]
            if card.get('resource-id', '').endswith(':id/ll_main'):
                break
        # 卡片里的 text_content 才是这一段要读的文字
        for c in card.iter('node'):
            if c.get('resource-id', '').endswith(':id/text_content') and c.get('text'):
                current = c.get('text')
                break
    return n, total, current


class Reader:
    def __init__(self, serial, voice, rate, out_dev, gain=1.0, submit=False,
                 max_segments=0, verbose=True):
        self.d = u2.connect(serial)
        self.voice = voice
        self.rate = rate
        self.out_dev = out_dev
        self.gain = gain
        self.submit = submit
        self.max_segments = max_segments
        self.verbose = verbose
        self.done = 0

    # ---------- 页面信息 ----------
    def page_info(self):
        """返回 (当前段号, 总段数, 当前段文本)。"""
        return parse_page(self.d.dump_hierarchy())

    def next_btn(self):
        return self.d(resourceId=rid('tv_next_question'))

    def btn_enabled(self):
        try:
            return bool(self.next_btn().info.get('enabled'))
        except Exception:
            return False

    def shot(self, name):
        os.makedirs(SHOT_DIR, exist_ok=True)
        path = os.path.join(SHOT_DIR, name)
        self.d.screenshot(path)
        return path

    # ---------- 语音 ----------
    def synth(self, text):
        asyncio.run(edge_tts.Communicate(text, self.voice, rate=self.rate).save(TMP_MP3))

    def play(self):
        data, sr = sf.read(TMP_MP3, always_2d=False)
        if data.ndim == 1:
            data = data[:, None]
        if sr != OUT_SR:
            data = ss.resample_poly(data, OUT_SR, sr)
        if self.gain != 1.0:
            data = np.clip(data * self.gain, -1.0, 1.0)
        sd.play(data, OUT_SR, device=self.out_dev)
        sd.wait()

    # ---------- 录音 ----------
    def start_recording(self, timeout=12):
        """点录音键，直到界面上出现波纹布局 layout_recording。"""
        end = time.time() + timeout
        while time.time() < end:
            if self.d(resourceId=rid('layout_recording')).exists:
                return True
            if self.d(resourceId=rid('iv_record')).exists:
                self.d(resourceId=rid('iv_record')).click()
            time.sleep(0.5)
        return self.d(resourceId=rid('layout_recording')).exists

    def stop_recording(self):
        """点波纹布局本身结束录音（这是 App 认的停止入口）。"""
        self.d(resourceId=rid('layout_recording')).click()

    def record_segment(self):
        """录当前这一段。已录过则跳过。返回 (段号, 总段数, 是否新录)。"""
        n, total, text = self.page_info()
        if n is None:
            raise RuntimeError('读不到段号，可能不在朗读页或 App 版本不匹配')
        if self.btn_enabled():
            self.log('段 %s/%s 已有录音，跳过' % (n, total))
            return n, total, False

        if not text:
            raise RuntimeError('读不到第 %s 段文本，请确认停在录音页' % n)

        self.log('段 %s/%s 朗读：%s' % (n, total, text[:24]))
        self.synth(text)
        if not self.start_recording():
            raise RuntimeError('点录音键后没有进入录音状态')
        time.sleep(0.4)
        self.play()
        time.sleep(0.5)
        self.stop_recording()
        self.done += 1
        return n, total, True

    # ---------- 流程 ----------
    def run_one(self):
        n, total, recorded = self.record_segment()
        self.shot('one_seg.png')
        self.log('当前段处理完成（%s/%s），截图 shots/one_seg.png' % (n, total))
        return n, total

    def run_full(self):
        while True:
            n, total, recorded = self.record_segment()

            if self.max_segments and self.done >= self.max_segments:
                self.log('已达 --max-segments 上限，停止')
                self.shot('limit.png')
                return

            if n >= total:
                time.sleep(1.2)
                btn = self.next_btn()
                if btn.exists and self.btn_enabled():
                    btn.click()
                self.log('全部 %s 段已完成' % total)
                time.sleep(1.5)
                self.shot('finish_page.png')
                if self.submit:
                    self._click_submit()
                else:
                    self.log('已停在交卷页，截图 shots/finish_page.png，请人工确认后提交')
                return

            # 推进到下一段：有的页面录完自动跳，有的需要点“确定”
            target = n + 1
            end = time.time() + 25
            progressed = False
            while time.time() < end:
                n2, _, _ = self.page_info()
                if n2 == target:
                    progressed = True
                    break
                btn = self.next_btn()
                if btn.exists and self.btn_enabled():
                    btn.click()
                    time.sleep(0.8)
                time.sleep(0.4)
            if not progressed:
                self.shot('stuck.png')
                self.log('卡在第 %s 段，未能进入第 %s 段，已截图 shots/stuck.png' % (n, target))
                return

    def _click_submit(self):
        """点“提交作业”，处理可能出现的二次确认弹窗。"""
        for name in ('tv_submit', 'btn_submit', 'tv_next_question'):
            if self.d(resourceId=rid(name)).exists:
                self.d(resourceId=rid(name)).click()
                time.sleep(1.2)
                break
        else:
            # 兜底：按文字点
            if self.d(text='提交作业').exists:
                self.d(text='提交作业').click()
                time.sleep(1.2)
        # 二次确认
        for t in ('确认提交', '确定', '提交'):
            obj = self.d(text=t)
            if obj.exists:
                obj.click()
                time.sleep(1.0)
                break
        self.shot('after_submit.png')
        self.log('已尝试提交，截图 shots/after_submit.png')

    def log(self, msg):
        if self.verbose:
            print(msg, flush=True)


def main():
    ap = argparse.ArgumentParser(
        description='智学网学生端「文章朗读」自动完成脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='音色可选：' + '、'.join('%s=%s' % (k, v) for k, v in VOICES.items()))
    ap.add_argument('--mode', choices=['one', 'full'], default='one',
                    help='one=只录当前段（验证用，默认）；full=录到最后')
    ap.add_argument('--serial', default=DEFAULT_SERIAL,
                    help='模拟器 adb 地址，默认 %s' % DEFAULT_SERIAL)
    ap.add_argument('--voice', default='zh-CN-YunjianNeural',
                    help='edge-tts 音色，默认男声 zh-CN-YunjianNeural')
    ap.add_argument('--rate', default='-5%',
                    help='语速，默认 -5%%，略慢更接近朗读')
    ap.add_argument('--gain', type=float, default=1.0,
                    help='音量增益，录音太小可调 1.2~1.6')
    ap.add_argument('--device', type=int, default=None,
                    help='手动指定输出设备编号（默认自动找 CABLE Input）')
    ap.add_argument('--out-hint', default='CABLE Input',
                    help='自动查找输出设备时的关键字')
    ap.add_argument('--submit', action='store_true',
                    help='录完后自动点“提交作业”（默认不提交）')
    ap.add_argument('--max-segments', type=int, default=0,
                    help='最多录几段后停止，0=不限')
    args = ap.parse_args()

    out_dev = args.device if args.device is not None \
        else resolve_output_device(args.out_hint)

    try:
        reader = Reader(
            serial=args.serial,
            voice=args.voice,
            rate=args.rate,
            out_dev=out_dev,
            gain=args.gain,
            submit=args.submit,
            max_segments=args.max_segments,
        )
    except Exception as e:
        print('[失败] 连不上模拟器 %s：%s' % (args.serial, e), flush=True)
        print('  · 确认模拟器已启动，且已开启 ADB 调试', flush=True)
        print('  · 用 --serial 指定正确地址（adb devices 可查看）', flush=True)
        sys.exit(1)

    try:
        if args.mode == 'one':
            reader.run_one()
        else:
            reader.run_full()
    except KeyboardInterrupt:
        print('\n[中断] 已停止', flush=True)
        sys.exit(130)
    except Exception as e:
        print('[失败] %s' % e, flush=True)
        try:
            reader.shot('error.png')
            print('已截图 shots/error.png', flush=True)
        except Exception:
            pass
        sys.exit(1)


if __name__ == '__main__':
    main()
