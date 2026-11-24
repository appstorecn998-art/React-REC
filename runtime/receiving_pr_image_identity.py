"""Compare verified page content; names and compression are representations."""
from receiving_image_archive import image_name,source_digest,sha


def _aliases(images):
    images=list(images)
    if not images or len({image_name(p) for p in images})!=len(images):return None
    result=[{source_digest(p),sha(p)} for p in images]
    if len({source_digest(p) for p in images})!=len(images):return None
    return result


def _match(left,right):
    if not left or not right or len(left)!=len(right):return False
    used=set()
    for values in left:
        matches=[i for i,current in enumerate(right) if i not in used and values&current]
        if len(matches)!=1:return False
        used.add(matches[0])
    return True


def pr_images_match(saved,images):
    if not isinstance(saved,dict):return False
    if len({image_name(name) for name in saved})!=len(saved):return False
    return _match([{value} for value in saved.values()],_aliases(images))


def same_pr_images(opened,current):return _match(_aliases(opened),_aliases(current))
