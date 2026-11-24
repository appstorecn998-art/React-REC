"""Non-destructive document previews. Never changes or saves the source image."""
from pathlib import Path
from PIL import Image, ImageOps, ImageStat
import numpy as np
import cv2

def document_crop(image):
    """Conservative page-boundary crop; uncertain boundaries retain the full image."""
    w,h=image.size
    scale=min(1.,1100/max(w,h))
    rgb=cv2.resize(np.asarray(image),(max(1,round(w*scale)),max(1,round(h*scale))),interpolation=cv2.INTER_AREA);gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    blur=cv2.GaussianBlur(gray,(5,5),0)
    edges=cv2.Canny(blur,35,110)
    edges=cv2.morphologyEx(edges,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    _,mask=cv2.threshold(blur,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    total=gray.size;candidates=[]
    for binary in (edges,mask):
        contours,_=cv2.findContours(binary,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area=cv2.contourArea(contour)
            if not .42*total<=area<=.96*total:continue
            poly=cv2.approxPolyDP(contour,.025*cv2.arcLength(contour,True),True)
            if len(poly)!=4 or not cv2.isContourConvex(poly):continue
            box=cv2.boundingRect(poly);x,y,bw,bh=box
            if bw<gray.shape[1]*.45 or bh<gray.shape[0]*.45:continue
            # A four-sided table inside a page is not a page boundary.
            inside=np.zeros_like(gray);cv2.fillConvexPoly(inside,poly,255)
            outer=cv2.dilate(inside,np.ones((17,17),np.uint8))
            ring=(outer>0)&(inside==0)
            if ring.sum()<200:continue
            interior=cv2.erode(inside,np.ones((17,17),np.uint8))>0
            if interior.sum()<200:continue
            contrast=float(np.median(gray[interior]))-float(np.median(gray[ring]))
            if contrast<14:continue
            if area/(bw*bh)<.78:continue
            # Retain generous safety margins around all edges including stamps.
            pad=max(12,round(max(w,h)*.025))
            bounds=(max(0,int(x/scale)-pad),max(0,int(y/scale)-pad),
                    min(w,int((x+bw)/scale)+pad),min(h,int((y+bh)/scale)+pad))
            retained=(bounds[2]-bounds[0])*(bounds[3]-bounds[1])/(w*h)
            if retained>.97:continue
            candidates.append((area,bounds))
    if not candidates:return image,None
    bounds=max(candidates,key=lambda item:item[0])[1]
    return image.crop(bounds),bounds

def brighten(image):
    gray=image.convert('L');hist=gray.histogram();count=sum(hist)
    acc=0;paper=255
    for i,n in enumerate(hist):
        acc+=n
        if acc>=count*.75:paper=i;break
    if paper>=220:return image.copy(),False
    # Gamma lifts shadows while retaining dark ink and colored annotations.
    gamma=max(.62,min(.94,paper/230))
    lut=[round(255*((i/255)**gamma)) for i in range(256)]
    result=image.point(lut*3)
    return result,True

def prepare_preview(path,light=True,crop=True):
    path=Path(path)
    with Image.open(path) as source:
        # Archive WebP pages are already upright; avoid Pillow's animation decoder.
        if source.format=='WEBP' and getattr(source,'n_frames',1)==1 and source.getexif().get(274,1)==1:
            decoded=cv2.imdecode(np.fromfile(path,dtype=np.uint8),cv2.IMREAD_COLOR)
            if decoded is None:raise ValueError('Không giải mã được ảnh: '+str(path))
            image=Image.fromarray(cv2.cvtColor(decoded,cv2.COLOR_BGR2RGB))
        else:
            ImageOps.exif_transpose(source,in_place=True)
            image=source.convert('RGB')
    original_size=image.size;bounds=None
    if crop:image,bounds=document_crop(image)
    changed=False
    if light:image,changed=brighten(image)
    if max(image.size)>2800:
        ratio=2800/max(image.size)
        size=tuple(max(1,round(n*ratio)) for n in image.size)
        image=Image.fromarray(cv2.resize(np.asarray(image),size,interpolation=cv2.INTER_AREA))
    return image,{'brightened':changed,'crop_box':bounds,'original_size':original_size,
                  'label':('Đã làm sáng' if changed else 'Giữ ánh sáng gốc')+
                      (' · Đã cắt viền' if bounds else ' · Giữ toàn khung')}
