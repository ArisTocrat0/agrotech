"""Conservative crop-row geometry from a downscaled vegetation mask (OpenCV C++)."""
import math
import cv2
import numpy as np


def estimate_rows(image, detector):
    size = image.size
    small = image.copy()
    small.thumbnail((768,768))
    mask = detector.mask(small)
    height,width = mask.shape
    edges = cv2.Canny(mask,50,150)
    lines = cv2.HoughLinesP(edges,1,np.pi/180,threshold=max(20,min(width,height)//8),
                            minLineLength=max(20,min(width,height)//4),maxLineGap=20)
    empty = {'count':None, 'confidence':0.0, 'lines':[], 'method':'vegetation_hough', 'requires_review':True}
    if lines is None:
        return empty
    segments = lines.reshape(-1,4).astype(float)
    delta = segments[:,2:]-segments[:,:2]
    lengths = np.linalg.norm(delta,axis=1)
    angles = np.arctan2(delta[:,1],delta[:,0]) % np.pi
    bins = np.linspace(0,np.pi,37)
    hist,_ = np.histogram(angles,bins,weights=lengths)
    dominant = (bins[hist.argmax()]+bins[hist.argmax()+1])/2
    distance = np.abs((angles-dominant+np.pi/2)%np.pi-np.pi/2)
    accepted = distance < np.deg2rad(8)
    confidence = float(lengths[accepted].sum()/lengths.sum())
    if confidence < .55:
        return empty
    theta = math.atan2(float((np.sin(2*angles[accepted])*lengths[accepted]).sum()),
                       float((np.cos(2*angles[accepted])*lengths[accepted]).sum()))/2
    direction = np.array([math.cos(theta),math.sin(theta)])
    normal = np.array([-direction[1],direction[0]])
    positions = sorted(float(((s[:2]+s[2:])/2) @ normal) for s in segments[accepted])
    clusters = []
    gap = max(6,min(width,height)*.025)
    for rho in positions:
        if not clusters or rho-np.mean(clusters[-1]) > gap:
            clusters.append([rho])
        else:
            clusters[-1].append(rho)
    if len(clusters) < 2:
        return empty
    output = []
    for cluster in clusters:
        point = normal*np.mean(cluster)
        extent = math.hypot(width,height)*2
        start,end = point-direction*extent,point+direction*extent
        ok,a,b = cv2.clipLine((0,0,width,height),tuple(np.rint(start).astype(int)),tuple(np.rint(end).astype(int)))
        if ok:
            output.append({'x1':a[0]*size[0]/width,'y1':a[1]*size[1]/height,
                           'x2':b[0]*size[0]/width,'y2':b[1]*size[1]/height})
    return {'count':len(output),'confidence':round(confidence,3),'lines':output,
            'method':'vegetation_hough','requires_review':True}
