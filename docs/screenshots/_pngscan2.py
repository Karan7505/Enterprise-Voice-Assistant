import struct, zlib, sys, os
from collections import Counter

def decode_png(path):
    data = open(path, 'rb').read()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    pos = 8; w=h=None; idat=b''
    while pos < len(data):
        ln = struct.unpack('>I', data[pos:pos+4])[0]
        typ = data[pos+4:pos+8]
        chunk = data[pos+8:pos+8+ln]
        if typ == b'IHDR':
            w, h, bitd, colort = struct.unpack('>IIBB', chunk[:10])
        elif typ == b'IDAT':
            idat += chunk
        elif typ == b'IEND':
            break
        pos += 12 + ln
    raw = zlib.decompress(idat)
    ch = {0:1, 2:3, 3:1, 4:2, 6:4}[colort]
    bpp = max(1, ch * (bitd // 8))
    stride = w * ch * (bitd // 8)
    out = bytearray(w * h * ch * (bitd // 8))
    prev = bytearray(stride)
    i = 0
    for y in range(h):
        f = raw[i]; i += 1
        line = bytearray(raw[i:i+stride]); i += stride
        if f == 1:
            for x in range(bpp, stride): line[x] = (line[x] + line[x-bpp]) & 255
        elif f == 2:
            for x in range(stride): line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                a = line[x-bpp] if x >= bpp else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x-bpp] if x >= bpp else 0
                b = prev[x]; c = prev[x-bpp] if x >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 255
        out[y*stride:(y+1)*stride] = line
        prev = line
    return w, h, ch, bitd, bytes(out)

def px(buf, ch, bitd, w, x, y):
    stride = w * ch * (bitd // 8)
    o = y * stride + x * ch
    if ch >= 3: return buf[o], buf[o+1], buf[o+2]
    return buf[o], buf[o], buf[o]

def analyze(path, label):
    w, h, ch, bitd, buf = decode_png(path)
    # capsule occupies screenshot x 1270..1770, y 4..779 (12.5x total scale)
    # sample central band only (away from rounded ends & inset rim highlights):
    # y from 30..750  (inset highlight ~ top 15px and bottom ~15px excluded at ends, band mid is safe)
    # interior column: exclude outer ~35px at left/right rims -> x 1310..1730
    white = []
    for y in range(30, 750):
        for x in range(1310, 1730):
            r,g,b = px(buf, ch, bitd, w, x, y)
            # runner/teeth cream ~ (255,250,243); test lenient near-white
            if r > 235 and g > 225 and b > 210:
                white.append((x, y))
    print(f'== {label}: near-white px in capsule interior band: {len(white)}')
    if white:
        xs=[p[0] for p in white]; ys=[p[1] for p in white]
        print('   x', min(xs), '..', max(xs), ' y', min(ys), '..', max(ys))
        print('   col counts:', Counter(x for x,_ in white).most_common(10))
        print('   row counts:', Counter(y for _,y in white).most_common(10))
    else:
        print('   -> interior band has NO near-white pixels')

base = r'C:\Projects\Enterprise-Voice-Assistant\docs\screenshots'
analyze(os.path.join(base, '_tmp-zoom-c.png'), 'zoom-c 1st')
analyze(os.path.join(base, '_tmp-zoom-c2.png'), 'zoom-c2 2nd')
