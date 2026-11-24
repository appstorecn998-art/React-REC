"""Fast local grid rectification. Warps the full photograph without trimming content."""
import cv2,numpy as np
from PIL import Image

VERSION='paper-boundary-v8-deskew-line-consensus'

def lines(image):
    scale=min(1,1200/max(image.size));a=np.asarray(image.resize((round(image.width*scale),round(image.height*scale))))
    g=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY);edges=cv2.Canny(g,40,120)
    found=cv2.HoughLinesP(edges,1,np.pi/1800,70,minLineLength=min(g.shape)*.25,maxLineGap=25)
    return ([] if found is None else found.reshape(-1,4).astype(float)),scale,g.shape

def straighten(image):
    from paper_crop import crop_paper
    paper,cropped=crop_paper(image)
    result,method=rectify_grid(paper)
    return result,('paper-crop+'+method) if cropped else method

def rectify_grid(image):
    ls,scale,(h,w)=lines(image);hs=[];vs=[]
    for x,y,xx,yy in ls:
        dx=xx-x;dy=yy-y
        if abs(dx)>w*.45 and abs(dy)<abs(dx)*.15:
            hs.append((dy/dx,y-dy/dx*x,(y+yy)/2))
        if abs(dy)>h*.23 and abs(dx)<abs(dy)*.18:
            vs.append((dx/dy,x-dx/dy*y,min(y,yy),max(y,yy)))
    matrix=None;method='original'
    if len(hs)>=5 and len(vs)>=4:
        # Table columns share both endpoints; this excludes the paper's outer edge.
        groups=[[v for v in vs if abs(v[2]-seed[2])<h*.045 and abs(v[3]-seed[3])<h*.045] for seed in vs]
        columns=max(groups,key=len)
        if len(columns)>=4:
            top=float(np.median([v[2] for v in columns]));bottom=float(np.median([v[3] for v in columns]));middle=(top+bottom)/2
            left=min(columns,key=lambda v:v[0]*middle+v[1]);right=max(columns,key=lambda v:v[0]*middle+v[1])
            horizontal=[v for v in hs if top-h*.03<=v[2]<=bottom+h*.03]
            if horizontal and (right[0]*middle+right[1])-(left[0]*middle+left[1])>w*.5:
                upper=min(horizontal,key=lambda v:abs(v[2]-top));lower=min(horizontal,key=lambda v:abs(v[2]-bottom))
                def cross(v,hline):
                    a,b=v[:2];c,d=hline[:2];y=(c*b+d)/(1-c*a);return [a*y+b,y]
                quad=np.array([cross(left,upper),cross(right,upper),cross(right,lower),cross(left,lower)],np.float32)/scale
                tw=(np.linalg.norm(quad[1]-quad[0])+np.linalg.norm(quad[2]-quad[3]))/2
                th=(np.linalg.norm(quad[3]-quad[0])+np.linalg.norm(quad[2]-quad[1]))/2
                if tw>image.width*.45 and th>image.height*.18:
                    dest=np.array([[0,0],[tw,0],[tw,th],[0,th]],np.float32)
                    matrix=cv2.getPerspectiveTransform(quad,dest);method='table-perspective'
    if matrix is None and len(hs)>=3:
        # Hough often finds several segments on the two edges of one printed line.
        # Group at the center of the image so each distinct line has one vote.
        bands=sorted((slope*w/2+offset,slope) for slope,offset,_ in hs)
        groups=[]
        for y,slope in bands:
            if not groups or y-groups[-1][0]>max(2,h*.008):
                groups.append((y,[]))
            groups[-1][1].append(slope)
        slopes=np.array([np.median(group) for _,group in groups])
        median=float(np.median(slopes));inliers=slopes[abs(slopes-median)<.015]
        if len(inliers)>=2:
            angle=float(np.degrees(np.arctan(np.median(inliers))))
            if .15<abs(angle)<8:
                matrix=np.vstack([cv2.getRotationMatrix2D((image.width/2,image.height/2),angle,1),[0,0,1]]);method='deskew'
    if matrix is None:return image,method
    corners=np.array([[[0,0],[image.width,0],[image.width,image.height],[0,image.height]]],np.float32)
    denominators=np.c_[corners[0],np.ones(4)]@matrix[2]
    if np.any(denominators<=.05):return image,'original'
    warped=cv2.perspectiveTransform(corners,matrix)[0];lo=warped.min(0);hi=warped.max(0);size=np.ceil(hi-lo).astype(int)
    if np.any(size<=0) or size[0]>image.width*1.6 or size[1]>image.height*1.6:return image,'original'
    matrix=np.array([[1,0,-lo[0]],[0,1,-lo[1]],[0,0,1]])@matrix
    # Match the photographed paper tone without extending edge text into the padding.
    pixels=np.asarray(image)
    paper=tuple(float(c) for c in np.median(pixels.reshape(-1,3)[::32],axis=0))
    result=cv2.warpPerspective(pixels,matrix,tuple(size),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_CONSTANT,borderValue=paper)
    return Image.fromarray(result),method
