"""エレベーター内でサラリーマンが浮き上がる 9:16 動画を生成する。

使い方: python3 elevator/make_video.py [出力パス]
必要: Pillow, numpy, ffmpeg, IPAゴシック
"""
import math
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
FPS = 30
DURATION = 6.5
FONT = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"

# 奥の壁
BX0, BX1, BY0, BY1 = 200, 880, 420, 1500
RAIL_Y = 1180
FLOOR_Y = 1760

T_FLOAT = 0.7     # 浮き始め・「しかし」
T_GRAB = 2.4      # 「手すりにつかまり」・手を伸ばす
T_HOLD = 3.2      # つかまり完了

NAVY = (38, 48, 78)
NAVY_D = (26, 33, 56)
SKIN = (246, 206, 172)
SKIN_D = (220, 172, 138)
HAIR = (30, 26, 24)


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def lerp(a, b, t):
    return a + (b - a) * t


def lerp2(p, q, t):
    return (lerp(p[0], q[0], t), lerp(p[1], q[1], t))


# ---------------------------------------------------------------- 背景

def build_background():
    rng = np.random.default_rng(1)
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)

    # 天井・床・側壁
    d.polygon([(0, 0), (W, 0), (BX1, BY0), (BX0, BY0)], fill=(70, 72, 78))
    d.polygon([(BX0, BY1), (BX1, BY1), (W, H), (0, H)], fill=(92, 80, 70))
    d.polygon([(0, 0), (BX0, BY0), (BX0, BY1), (0, H)], fill=(150, 154, 160))
    d.polygon([(W, 0), (BX1, BY0), (BX1, BY1), (W, H)], fill=(140, 144, 150))

    arr = np.asarray(img).astype(np.float32)

    # 奥の壁: ヘアライン仕上げのステンレス
    bw, bh = BX1 - BX0, BY1 - BY0
    cols = rng.normal(0, 7, bw)
    grad = np.linspace(0, 1, bw)
    base = 178 + 22 * np.exp(-((grad - 0.5) / 0.28) ** 2) + cols
    wall = np.repeat(base[None, :], bh, 0) + rng.normal(0, 2, (bh, bw))
    arr[BY0:BY1, BX0:BX1] = np.stack([wall, wall + 2, wall + 6], -1)

    # 側壁・床にノイズ
    noise = rng.normal(0, 4, (H, W, 1))
    mask = np.ones((H, W, 1), np.float32)
    mask[BY0:BY1, BX0:BX1] = 0
    arr += noise * mask
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)

    # 床の市松
    for i in range(1, 6):
        f = i / 6
        y = lerp(BY1, H, f ** 1.6)
        xl = lerp(BX0, 0, (y - BY1) / (H - BY1))
        d.line([(xl, y), (W - xl, y)], fill=(78, 68, 60), width=3)
    for i in range(1, 8):
        x0 = lerp(BX0, BX1, i / 8)
        x1 = lerp(0, W, i / 8)
        d.line([(x0, BY1), (x1, H)], fill=(78, 68, 60), width=3)

    # 奥の壁の継ぎ目（中央は扉）
    d.line([(540, BY0 + 140), (540, BY1)], fill=(120, 124, 130), width=4)
    d.rectangle([BX0 + 20, BY0 + 140, BX1 - 20, BY1], outline=(130, 134, 140), width=4)

    # 天井の照明
    d.rounded_rectangle([340, 120, 740, 250], 20, fill=(235, 238, 230))
    d.rounded_rectangle([330, 110, 750, 260], 24, outline=(110, 112, 116), width=6)

    # 壁と床の境目
    for a, b in [((0, 0), (BX0, BY0)), ((W, 0), (BX1, BY0)),
                 ((BX0, BY1), (0, H)), ((BX1, BY1), (W, H))]:
        d.line([a, b], fill=(60, 60, 64), width=4)
    d.rectangle([BX0, BY0, BX1, BY1], outline=(90, 92, 98), width=4)

    # 操作盤（右の側壁）
    d.polygon([(960, 900), (1010, 870), (1010, 1280), (960, 1260)], fill=(60, 62, 68))
    for k in range(6):
        y = 930 + k * 55
        d.ellipse([975, y - 8 * (1 + 0.02 * k), 995, y + 12], fill=(220, 210, 160))

    # 手すり
    def rail(points, w):
        for width, col in [(w, (90, 92, 98)), (w - 6, (190, 194, 200)), (w - 14, (245, 247, 250))]:
            d.line(points, fill=col, width=width)

    for x in (300, 780):
        d.rectangle([x - 8, RAIL_Y - 4, x + 8, RAIL_Y + 34], fill=(120, 122, 128))
    rail([(BX0, RAIL_Y), (BX1, RAIL_Y)], 24)
    side_y = lerp(0, H, (RAIL_Y - BY0) / (BY1 - BY0))
    rail([(BX0, RAIL_Y), (0, side_y)], 30)
    rail([(BX1, RAIL_Y), (W, side_y)], 30)

    # 照明のにじみ
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([200, -200, 880, 700], fill=60)
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    img = Image.composite(Image.new("RGB", (W, H), (255, 252, 235)), img, glow)
    return img


# ---------------------------------------------------------------- 人物

class Body:
    """腰を原点とするローカル座標を回転・平行移動してワールド座標に描く。"""

    def __init__(self, draw, hip, angle_deg, scale=1.0):
        self.d = draw
        self.hx, self.hy = hip
        self.a = math.radians(angle_deg)
        self.s = scale
        self.c, self.sn = math.cos(self.a), math.sin(self.a)

    def w(self, p):
        x, y = p[0] * self.s, p[1] * self.s
        return (self.hx + x * self.c + y * self.sn, self.hy - x * self.sn + y * self.c)

    def local(self, p):
        x, y = p[0] - self.hx, p[1] - self.hy
        return ((x * self.c - y * self.sn) / self.s, (x * self.sn + y * self.c) / self.s)

    def poly(self, pts, fill, outline=None, width=0):
        self.d.polygon([self.w(p) for p in pts], fill=fill, outline=outline, width=width)

    def circle(self, c, r, fill, outline=None, width=0):
        x, y = self.w(c)
        r *= self.s
        self.d.ellipse([x - r, y - r, x + r, y + r], fill=fill, outline=outline, width=width)

    def limb(self, a, b, width, fill):
        pa, pb = self.w(a), self.w(b)
        self.d.line([pa, pb], fill=fill, width=int(width * self.s))
        r = width * self.s / 2
        for x, y in (pa, pb):
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=fill)

    def line(self, pts, fill, width):
        self.d.line([self.w(p) for p in pts], fill=fill, width=max(1, int(width * self.s)), joint="curve")


def elbow(shoulder, hand, upper=165, lower=160, bend=1):
    dx, dy = hand[0] - shoulder[0], hand[1] - shoulder[1]
    dist = math.hypot(dx, dy)
    if dist >= upper + lower - 1:
        f = upper / (upper + lower)
        return (shoulder[0] + dx * f, shoulder[1] + dy * f)
    dist = max(dist, 1e-3)
    a = (upper ** 2 - lower ** 2 + dist ** 2) / (2 * dist)
    h = math.sqrt(max(upper ** 2 - a ** 2, 0))
    mx, my = shoulder[0] + dx * a / dist, shoulder[1] + dy * a / dist
    return (mx - bend * h * dy / dist, my + bend * h * dx / dist)


def draw_man(d, hip, angle, hands_local, knee, tie_float, panic, t):
    b = Body(d, hip, angle)
    sh_l, sh_r = (-88, -268), (88, -268)

    # 脚（膝の曲げ量 knee は 0〜1）
    for side in (-1, 1):
        hipj = (side * 38, 0)
        kn = (side * 42 + knee * 70, 200 - knee * 40)
        ft = (side * 44 + knee * 10 + side * knee * 20, 400 - knee * 60)
        b.limb(hipj, kn, 78, NAVY_D)
        b.limb(kn, ft, 72, NAVY_D)
        b.poly([(ft[0] - 38, ft[1] - 10), (ft[0] + 42 * 1, ft[1] - 10),
                (ft[0] + 50, ft[1] + 22), (ft[0] - 38, ft[1] + 22)], fill=(20, 18, 18))

    # 胴体（ジャケット）
    b.poly([(-100, -285), (100, -285), (90, 40), (-90, 40)], fill=NAVY)
    b.poly([(-42, -285), (42, -285), (0, -150)], fill=(250, 250, 252))
    # ネクタイ: 無重力でひらひら
    sway = math.sin(t * 7) * 12 * tie_float
    tip = (sway - 60 * tie_float, -60 - 170 * tie_float)
    mid = (sway * 0.5 - 20 * tie_float, -150 - 40 * tie_float)
    b.poly([(-14, -276), (14, -276), (mid[0] + 18, mid[1]), (tip[0] + 16, tip[1]),
            (tip[0], tip[1] + 26 * (1 - tie_float) - 10 * tie_float),
            (tip[0] - 16, tip[1]), (mid[0] - 18, mid[1])], fill=(196, 30, 40))
    b.poly([(-16, -285), (16, -285), (10, -264), (-10, -264)], fill=(160, 20, 30))
    # 襟
    b.poly([(-42, -285), (-100, -285), (-60, -120), (-12, -200)], fill=NAVY_D)
    b.poly([(42, -285), (100, -285), (60, -120), (12, -200)], fill=NAVY_D)
    for y in (-70, 0):
        b.circle((0, y), 6, (200, 200, 200))
    b.line([(-90, 40), (90, 40)], NAVY_D, 6)

    # 首・頭
    b.poly([(-24, -300), (24, -300), (22, -280), (-22, -280)], fill=SKIN_D)
    head = (0, -385)
    b.circle((-74, -380), 16, SKIN_D)
    b.circle((74, -380), 16, SKIN_D)
    b.circle(head, 76, SKIN)
    # 髪（七三分け、浮くと逆立つ）
    up = 30 * panic
    b.poly([(-78, -390), (-74, -440), (-40, -470 - up), (10, -478 - up * 1.2),
            (60, -462 - up), (80, -420), (78, -392), (60, -430), (-20, -436), (-60, -420)],
           fill=HAIR)
    b.line([(-20, -470 - up), (-30, -440)], (70, 64, 60), 3)
    # メガネ
    for ex in (-30, 30):
        b.circle((ex, -385), 22, None, outline=(30, 30, 30), width=5)
    b.line([(-8, -387), (8, -387)], (30, 30, 30), 5)
    # 目
    eye_r = 6 + 4 * panic
    for ex in (-30, 30):
        b.circle((ex, -384), eye_r, (20, 20, 20))
    # 眉（驚くと上がる）
    for side in (-1, 1):
        b.line([(side * 46, -414 - 14 * panic), (side * 16, -418 - 18 * panic + 10 * (1 - panic))],
               HAIR, 6)
    # 口: 平常→驚きの「O」
    if panic < 0.3:
        b.line([(-18, -338), (18, -338)], (130, 60, 60), 5)
    else:
        b.circle((0, -336), 8 + 10 * panic, (120, 30, 40))
    # 汗
    if panic > 0.5:
        sx, sy = 92, -420 + (t * 120) % 40
        b.poly([(sx, sy - 22), (sx + 12, sy), (sx, sy + 12), (sx - 12, sy)], fill=(140, 200, 255))

    # 腕
    for sh, hand in ((sh_l, hands_local[0]), (sh_r, hands_local[1])):
        bend = -1 if sh[0] < 0 else 1
        el = elbow(sh, hand, bend=bend)
        b.limb(sh, el, 62, NAVY)
        b.limb(el, hand, 56, NAVY)
        b.circle(hand, 9, (250, 250, 252))
        b.circle(hand, 26, SKIN)
    return b


def draw_briefcase(d, center, angle):
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))

    def tr(p):
        return (center[0] + p[0] * c + p[1] * s, center[1] - p[0] * s + p[1] * c)

    d.polygon([tr(p) for p in [(-30, -95), (30, -95), (30, -70), (-30, -70)]], outline=(40, 26, 18), width=10)
    d.polygon([tr(p) for p in [(-110, -75), (110, -75), (110, 70), (-110, 70)]], fill=(92, 58, 34))
    d.line([tr((-110, -20)), tr((110, -20))], fill=(60, 38, 22), width=6)
    for x in (-60, 60):
        d.polygon([tr(p) for p in [(x - 10, -30), (x + 10, -30), (x + 10, -10), (x - 10, -10)]],
                  fill=(210, 180, 90))


# ---------------------------------------------------------------- 字幕

def caption_image(text, size, color):
    font = ImageFont.truetype(FONT, size)
    pad = 40
    l, tp, r, bt = font.getbbox(text, stroke_width=14)
    img = Image.new("RGBA", (r - l + pad * 2, bt - tp + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((pad - l + 8, pad - tp + 10), text, font=font, fill=(0, 0, 0, 170),
                                stroke_width=14, stroke_fill=(0, 0, 0, 170))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(6)))
    # 太字に見せるため少しずらして重ね描き
    for dx in (0, 2):
        d.text((pad - l + dx, pad - tp), text, font=font, fill=color, stroke_width=14, stroke_fill=(10, 10, 10))
    return img


def paste_caption(frame, cap, cy, t, t0):
    k = clamp((t - t0) / 0.22)
    if k <= 0:
        return
    scale = 1 + 0.45 * (1 - ease_out(k)) ** 2 - 0.08 * math.sin(k * math.pi)
    im = cap.resize((max(1, int(cap.width * scale)), max(1, int(cap.height * scale))), Image.LANCZOS)
    if k < 1:
        a = im.getchannel("A").point(lambda v: int(v * ease_out(k)))
        im.putalpha(a)
    frame.alpha_composite(im, (int(W / 2 - im.width / 2), int(cy - im.height / 2)))


# ---------------------------------------------------------------- タイムライン

def render(t, bg, caps, digit_font):
    frame = bg.copy()
    d = ImageDraw.Draw(frame)

    # 階数表示（落下中は急速に減る）
    fall = max(0.0, t - T_FLOAT)
    floor = max(1, int(32 - fall * fall * 2.2 - fall * 1.5))
    d.rounded_rectangle([440, 440, 640, 540], 12, fill=(16, 14, 14), outline=(90, 90, 96), width=4)
    if t < T_FLOAT or int(t * 6) % 2 == 0:
        d.polygon([(470, 470), (510, 470), (490, 505)], fill=(255, 70, 50))
    d.text((600, 490), f"{floor:2d}", font=digit_font, fill=(255, 70, 50), anchor="rm")

    # 人物のポーズ
    stand_hip = (540, FLOOR_Y - 400)
    float_hip = (585, 1000)
    hold_hip = (610, 1000)
    stand_hands = [(-118, 40), (118, 40)]
    flail = 0.0

    f = ease_out((t - T_FLOAT) / (T_GRAB - T_FLOAT))
    g = ease((t - T_GRAB) / (T_HOLD - T_GRAB))
    wob = math.sin(t * 3.1)

    hip = lerp2(stand_hip, float_hip, f)
    hip = (hip[0] + 14 * wob * f, hip[1] + 18 * math.sin(t * 2.3) * f)
    angle = lerp(0, -12 + 8 * wob, f)
    knee = 0.55 * f
    if g > 0:
        hip = lerp2(hip, (hold_hip[0] + 10 * math.sin(t * 1.7), hold_hip[1] + 14 * math.sin(t * 2.2)), g)
        angle = lerp(angle, 88 + 6 * math.sin(t * 1.9), g)
        knee = lerp(knee, 0.25 + 0.2 * math.sin(t * 2.6), g)
    flail = f * (1 - g)

    panic = clamp((t - T_FLOAT) / 0.4)
    tmp = Body(d, hip, angle)
    flail_hands = [(-230 + 40 * math.sin(t * 9), -330 + 50 * math.cos(t * 8)),
                   (230 + 40 * math.sin(t * 8 + 1), -320 + 50 * math.cos(t * 9 + 2))]
    grip = [tmp.local((335, RAIL_Y - 2)), tmp.local((420, RAIL_Y - 2))]
    hands = []
    for i in range(2):
        p = lerp2(stand_hands[i], flail_hands[i], ease(flail * 1.5 if g == 0 else 1))
        hands.append(lerp2(p, grip[i], g))

    # 鞄: 最初は右手に、浮いたら手を離れて漂う
    hand_r = tmp.w(hands[1])
    case_hold = (hand_r[0] + 10, hand_r[1] + 100)
    drift = max(0.0, t - T_FLOAT - 0.15)
    case_free = (stand_hip[0] + 140 + 60 * drift, stand_hip[1] + 140 - 150 * drift + 16 * drift * drift)
    case_free = (min(case_free[0], 840), max(case_free[1], 760))
    cf = ease(drift / 0.5)
    case_pos = lerp2(case_hold, case_free, cf)
    case_angle = -40 * drift - 10 * math.sin(t * 2)

    # 影
    shadow = Image.new("L", (W, H), 0)
    sw = 230 * (1 - 0.6 * f)
    ImageDraw.Draw(shadow).ellipse([hip[0] - sw, FLOOR_Y - 20, hip[0] + sw, FLOOR_Y + 30],
                                   fill=int(140 * (1 - 0.7 * f)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    frame.paste((30, 24, 20), (0, 0), shadow)
    d = ImageDraw.Draw(frame)

    if cf > 0.5:
        draw_briefcase(d, case_pos, case_angle)
    draw_man(d, hip, angle, hands, knee, ease((t - T_FLOAT) / 0.8), panic, t)
    if cf <= 0.5:
        draw_briefcase(d, case_pos, case_angle * cf)

    # 非常灯の赤い明滅
    if t > T_FLOAT:
        pulse = 0.5 + 0.5 * math.sin((t - T_FLOAT) * 9)
        red = Image.new("RGB", (W, H), (255, 30, 20))
        frame = Image.blend(frame, red, 0.06 + 0.07 * pulse)

    # 揺れ（少し拡大して端を隠す）
    shake = clamp((t - T_FLOAT) / 0.1) * (1.0 - 0.6 * clamp((t - T_HOLD) / 1.5))
    dx = shake * (9 * math.sin(t * 53) + 5 * math.sin(t * 31))
    dy = shake * (8 * math.cos(t * 47) + 4 * math.sin(t * 29))
    z = 1.04
    frame = frame.transform((W, H), Image.AFFINE,
                            (1 / z, 0, (W - W / z) / 2 + dx, 0, 1 / z, (H - H / z) / 2 + dy),
                            resample=Image.BILINEAR)

    # ビネット + 字幕
    out = frame.convert("RGBA")
    out.alpha_composite(VIGNETTE)
    paste_caption(out, caps[0], 190, t, T_FLOAT)
    paste_caption(out, caps[1], 345, t, T_GRAB)
    return out.convert("RGB")


def make_vignette():
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.62)) ** 2)
    a = np.clip((r - 0.6) * 260, 0, 170).astype(np.uint8)
    v = np.zeros((H, W, 4), np.uint8)
    v[..., 3] = a
    return Image.fromarray(v, "RGBA")


VIGNETTE = make_vignette()


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "elevator/elevator_float.mp4"
    bg = build_background()
    caps = [caption_image("しかし", 170, (255, 255, 255)),
            caption_image("手すりにつかまり", 118, (255, 232, 60))]
    digit_font = ImageFont.truetype(FONT, 64)

    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", out],
        stdin=subprocess.PIPE)
    for i in range(int(DURATION * FPS)):
        proc.stdin.write(render(i / FPS, bg, caps, digit_font).tobytes())
    proc.stdin.close()
    proc.wait()
    print("wrote", out)


if __name__ == "__main__":
    main()
