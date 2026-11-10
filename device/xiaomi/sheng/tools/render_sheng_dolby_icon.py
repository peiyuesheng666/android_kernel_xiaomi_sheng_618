#!/usr/bin/env python3
"""Render original double-D geometry for legacy icons and local visual review."""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw


def silhouette(size, foreground, background):
    image = Image.new('RGBA', (size*4, size*4), background)
    draw = ImageDraw.Draw(image)
    # Sample the same two cubic arcs used by the Android vector, including its gap.
    points = [(2,5),(4.06,5)]
    for a,b,c,d in [((4.06,5),(7.926,5),(11.06,8.134),(11.06,12)),
                     ((11.06,12),(11.06,15.866),(7.926,19),(4.06,19))]:
        for step in range(1,65):
            t=step/64; s=1-t
            points.append(tuple(s**3*a[i]+3*s*s*t*b[i]+3*s*t*t*c[i]+t**3*d[i] for i in range(2)))
    points.append((2,19))
    for side in (points,[(24-x,y) for x,y in points]):
        draw.polygon([(x*size*4/24,y*size*4/24) for x,y in side],fill=foreground)
    return image.resize((size,size),Image.Resampling.LANCZOS)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--preview-dir',type=Path,required=True)
    args=parser.parse_args()
    for density,scale in [('mdpi',1),('hdpi',1.5),('xhdpi',2),('xxhdpi',3),('xxxhdpi',4)]:
        for resource,base,name in [('drawable',24,'ic_dolby'),('mipmap',48,'ic_launcher')]:
            folder=args.source/'res'/(resource+'-'+density); folder.mkdir(exist_ok=True)
            silhouette(round(base*scale),'#302A3A',(0,0,0,0)).save(folder/(name+'.png'))
    args.preview_dir.mkdir(parents=True,exist_ok=True)
    preview=Image.new('RGB',(900,300),'#F7F2FA')
    for i,(fg,bg) in enumerate([('#302A3A','#E7E1F1'),('#EADFFF','#493565'),('#173F33','#B7F2DA')]):
        preview.paste(silhouette(240,fg,bg),(30+300*i,30))
    preview.save(args.preview_dir/'double-d-preview.png')


if __name__=='__main__':main()
