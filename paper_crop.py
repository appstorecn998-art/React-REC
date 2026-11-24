"""Local contrasting-paper boundary detection; no model training or generated content."""
import cv2,numpy as np
from PIL import Image

def clipped_side_quad(gray, lines):
    """Use long paper edges that separate the sheet from a darker background."""
    h, w = gray.shape
    sides = [[], []]
    for x, y, xx, yy in lines:
        length = abs(yy-y)
        if length < h*.32:
            continue
        slope = (xx-x)/(yy-y)
        offset = x-slope*y
        if not .025 < abs(slope) < .18 or min(y,yy) > h*.42:
            continue
        side = 0 if slope < 0 else 1
        if not (0 < offset < w*.14 if side == 0 else w*.86 < offset < w):
            continue
        rows = np.linspace(min(y,yy),max(y,yy),30).astype(int)
        columns = np.round(slope*rows+offset).astype(int)
        offset_pixels = max(4,round(w*.009))
        valid = (columns >= offset_pixels) & (columns < w-offset_pixels)
        if np.count_nonzero(valid) < 18:
            continue
        rows, columns = rows[valid], columns[valid]
        direction = 1 if side == 0 else -1
        inside = gray[rows,columns+direction*offset_pixels].astype(int)
        outside = gray[rows,columns-direction*offset_pixels].astype(int)
        if np.mean(inside-outside > 25) < .7:
            continue
        sides[side].append((length, slope, offset))
    if not any(sides):
        return None
    left = max(sides[0])[1:] if sides[0] else (0, 0)
    right = max(sides[1])[1:] if sides[1] else (0, w-1)
    margin = max(5,round(w*.012))
    return np.array([
        [max(0,left[1]-margin),0],
        [min(w-1,right[1]+margin),0],
        [min(w-1,right[0]*(h-1)+right[1]+margin),h-1],
        [max(0,left[0]*(h-1)+left[1]-margin),h-1],
    ],np.float32)


def crop_paper(image):
    scale=min(1,1000/max(image.size));a=np.asarray(image.resize((round(image.width*scale),round(image.height*scale))))
    h,w=a.shape[:2];hsv=cv2.cvtColor(a,cv2.COLOR_RGB2HSV)
    mask=cv2.inRange(hsv,np.array([0,0,110]),np.array([179,95,255]))
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((13,13),np.uint8))
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not contours:return image,False
    c=max(contours,key=cv2.contourArea)
    if cv2.contourArea(c)<h*w*.55:return image,False
    hull=cv2.convexHull(c);poly=cv2.approxPolyDP(hull,.018*cv2.arcLength(hull,True),True)
    if len(poly)!=4:return image,False
    pts=poly[:,0].astype(np.float32);s=pts.sum(1);d=np.diff(pts,axis=1).ravel()
    quad=pts[[s.argmin(),d.argmin(),s.argmax(),d.argmax()]]
    if len(np.unique(quad,axis=0))!=4:return image,False
    # Only remove a contrasting border connected to the outside, never a dark internal table.
    area=cv2.contourArea(quad)/(w*h)
    edge_fallback=not .55<area<.985
    if edge_fallback:
        # A photographed sheet can cross the frame while its upper side edges remain visible.
        gray=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY)
        edges=cv2.Canny(cv2.GaussianBlur(gray,(5,5),0),20,65)
        ls=cv2.HoughLinesP(edges,1,np.pi/1800,40,minLineLength=h*.10,maxLineGap=20)
        lines=[] if ls is None else ls.reshape(-1,4)
        sides=[[],[]]
        for x,y,xx,yy in lines:
            if abs(yy-y)<h*.1 or abs(xx-x)>abs(yy-y)*.2 or min(y,yy)>h*.1:continue
            slope=(xx-x)/(yy-y);offset=x-slope*y
            if max(x,xx)<w*.08:sides[0].append((slope,offset))
            if min(x,xx)>w*.92:sides[1].append((slope,offset))
        left=max(sides[0],key=lambda v:v[1],default=(0,0))
        right=min(sides[1],key=lambda v:v[1],default=(0,w-1))
        if left[0]<0 and right[0]>0:
            quad=np.array([[max(0,left[1]),0],[min(w-1,right[1]),0],[min(w-1,right[0]*(h-1)+right[1]),h-1],[max(0,left[0]*(h-1)+left[1]),h-1]],np.float32)
        else:
            quad=clipped_side_quad(gray,lines)
            if quad is None:return image,False
    else:
        # Fit the actual side contour, rather than the convex hull that can include stacked paper.
        filled=np.zeros((h,w),np.uint8);cv2.drawContours(filled,[c],-1,255,-1)
        for side in (0,1):
            points=[]
            for y in range(5,h-5,5):
                xs=np.flatnonzero(filled[y])
                if not len(xs):continue
                x=xs[0] if side==0 else xs[-1]
                in_strip=(2<x<w*.20) if side==0 else (w*.80<x<w-3)
                if in_strip:points.append((y,x))
            if len(points)<h*.04 or np.ptp(np.array(points)[:,0])<h*.35:continue
            vx,vy,y0,x0=cv2.fitLine(np.array(points,dtype=np.float32),cv2.DIST_WELSCH,0,.01,.01).ravel()
            if abs(vx)<.01:continue
            slope=vy/vx;offset=x0-slope*y0
            if abs(slope)>.2:continue
            for i in ((0,3) if side==0 else (1,2)):
                quad[i,0]=np.clip(slope*quad[i,1]+offset,0,w-1)
    inside=np.zeros((h,w),np.uint8);cv2.fillConvexPoly(inside,quad.astype(np.int32),255)
    outside=inside==0
    if outside.sum()<w*h*.012:return image,False
    # A broad shadow may split one receipt into two bright components; retain both sections.
    for other in contours:
        if other is c or cv2.contourArea(other)<w*h*.008:continue
        component=np.zeros((h,w),np.uint8);cv2.drawContours(component,[other],-1,255,-1)
        if np.count_nonzero((component>0)&outside)>w*h*.008:return image,False
    if not edge_fallback and np.median(hsv[:,:,2][outside])>np.median(hsv[:,:,2][inside>0])-25 and np.median(hsv[:,:,1][outside])<np.median(hsv[:,:,1][inside>0])+25:return image,False
    quad/=scale
    tw=round(max(np.linalg.norm(quad[1]-quad[0]),np.linalg.norm(quad[2]-quad[3])))
    th=round(max(np.linalg.norm(quad[3]-quad[0]),np.linalg.norm(quad[2]-quad[1])))
    if tw<image.width*.65 or th<image.height*.65:return image,False
    matrix=cv2.getPerspectiveTransform(quad,np.array([[0,0],[tw-1,0],[tw-1,th-1],[0,th-1]],np.float32))
    return Image.fromarray(cv2.warpPerspective(np.asarray(image),matrix,(tw,th),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)),True
