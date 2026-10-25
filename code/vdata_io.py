"""Standard-library VoxelXML integrity audit, no SDK, no dense voxel array."""
import base64
import hashlib
import math
from pathlib import Path
import struct
import xml.etree.ElementTree as ET
import zlib


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(1048576),b''):h.update(data)
    return h.hexdigest()


def field_integrity(text):
    data=base64.b64decode(''.join((text or '').split()),validate=True)
    position=0;decoded=0;blocks=0
    while position<len(data):
        if data[position:position+6]!=b'!zlib!' or len(data)-position<14:raise ValueError('Invalid !zlib! block header')
        raw_size,packed_size=struct.unpack('!II',data[position+6:position+14])
        end=position+14+packed_size
        if packed_size<=0 or end>len(data):raise ValueError('Truncated compressed block')
        decoder=zlib.decompressobj();tail=data[position+14:end];actual=0
        while tail:
            raw=decoder.decompress(tail,1048576);actual+=len(raw);tail=decoder.unconsumed_tail
        actual+=len(decoder.flush())
        if not decoder.eof or decoder.unused_data or actual!=raw_size:raise ValueError('Native zlib block checksum/size/eof mismatch')
        decoded+=actual;blocks+=1;position=end
    if not blocks:raise ValueError('Empty compressed payload')
    return {'compressed_bytes':len(data),'decoded_bytes':decoded,'zlib_blocks':blocks}


def audit_vdata(path,expected_voxel_um=None,require_planes=None):
    path=Path(path).resolve();before=sha256(path)
    root=ET.parse(str(path)).getroot()
    if root.tag!='VoxelXML':raise ValueError('Expected Coventor VoxelXML')
    p=root.find('Properties')
    if p is None:raise ValueError('Missing Properties')
    units={'um':1.,'nm':.001,'A':.0001,'µm':1.,'μm':1.}
    v=p.find('VoxelSize');dims=p.find('NumVoxels');origin=p.find('ModelOrigin')
    if v is None or dims is None or origin is None:raise ValueError('Incomplete grid metadata')
    h=float(v.get('Value'))*units[v.get('Units')]
    shape=[int(dims.get(n)) for n in ['NX','NY','NZ']]
    lower=[float(origin.get(n))*units[origin.get('Units')] for n in ['X','Y','Z']]
    if not math.isfinite(h) or h<=0 or any(n<=0 for n in shape):raise ValueError('Invalid grid dimensions/spacing')
    if not all(math.isfinite(x) for x in lower):raise ValueError('Invalid grid origin')
    count=shape[0]*shape[1]*shape[2]
    vox=[field_integrity(n.text) for n in root.iter('VoxelData')]
    if not vox or sum(n['decoded_bytes'] for n in vox)!=3*count:raise ValueError('Voxel payload must have 3 bytes per cell')
    planes=[field_integrity(n.text) for n in root.iter('PlaneEquations')]
    if planes and sum(n['decoded_bytes'] for n in planes)!=16*count:raise ValueError('Plane payload must have 16 bytes per cell')
    if expected_voxel_um is not None and abs(h-expected_voxel_um)>expected_voxel_um*1e-9:raise ValueError('Export resolution differs from requested model')
    if require_planes is True and not planes:raise ValueError('Requested plane equations are missing')
    if sha256(path)!=before:raise RuntimeError('VDATA changed while checking it')
    return {'file':str(path),'file_bytes':path.stat().st_size,'sha256':before,'xml_root':'VoxelXML',
            'voxel_size_um':h,'dimensions_xyz':shape,'voxel_count':count,'origin_um':lower,
            'bounds_um':[lower,[x+n*h for x,n in zip(lower,shape)]],
            'materials':[dict(n.attrib) for n in root.find('Materials')],
            'voxel_payloads':vox,'plane_equation_payloads':planes,'integrity_pass':True,
            'source_file_unchanged':True,'sdk_or_process_simulation_used':False,
            'limit':'Checks bytes, metadata and compression integrity. Not a fabrication calibration or optical accuracy certificate.'}
