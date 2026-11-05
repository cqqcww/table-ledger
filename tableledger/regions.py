"""Deterministic crops, with original page coordinates; never infer text locally."""
import base64
import hashlib
import uuid
from PIL import Image
from .documents import image_content
from .schema import compact_json


def views(doc, cache_dir, *, local=True, ir=None, max_crops=8):
    result=image_content(doc,10240000)
    if not local: return result
    candidates=[]
    if ir:
        for t in ir.get('tables',[]):
            for region in t.get('regions',[]): candidates.append(region)
    # Whole-page detail strips are independent of question IDs or filename patterns.
    if not candidates:
        for page,path in enumerate(doc.images,1):
            with Image.open(path) as im:
                w,h=im.size
            if max(w,h)>=1500:
                boxes=([0,0,1000,580],[0,420,1000,1000]) if h>=w else ([0,0,580,1000],[420,0,1000,1000])
                candidates.extend({'page':page,'bbox':list(b),'rotation':0} for b in boxes)
    cache_dir.mkdir(parents=True,exist_ok=True)
    for region in candidates[:max_crops]:
        page=region['page']; coords=region['bbox']; rotate=region.get('rotation',0)
        # Expand context, never replace/remove the full original page.
        x0,y0,x1,y1=coords
        box=[max(0,x0-35),max(0,y0-65),min(1000,x1+35),min(1000,y1+65)]
        fingerprint=hashlib.sha256((doc.images[page-1].as_posix()+compact_json([box,rotate])).encode()).hexdigest()
        dest=cache_dir/(fingerprint+'.jpg')
        if not dest.is_file():
            with Image.open(doc.images[page-1]) as im:
                w,h=im.size
                cut=im.crop((int(box[0]*w/1000),int(box[1]*h/1000),int(box[2]*w/1000),int(box[3]*h/1000)))
                if rotate: cut=cut.rotate(-rotate,expand=True)
                cut.thumbnail((2400,2400),Image.Resampling.LANCZOS)
                temporary=dest.with_name(dest.stem+'.'+uuid.uuid4().hex+'.tmp')
                try:
                    cut.save(temporary,'JPEG',quality=95)
                    temporary.replace(dest)
                finally: temporary.unlink(missing_ok=True)
        result.append({'type':'text','text':f'文档第{page}页的附加细节图，原图坐标{box}，顺时针旋转{rotate}度；定位以原始整页为准：'})
        result.append({'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(dest.read_bytes()).decode()},'max_pixels':5760000})
    return result
