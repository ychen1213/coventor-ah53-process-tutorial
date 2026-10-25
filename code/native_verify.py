"""Read completed saved process steps, measure and optionally export; no build."""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import traceback
import xml.etree.ElementTree as ET

_SEMulator3D_API_VERSION='9.3'
from voxelModeler import *
from voxelWafer import *
from vdata_io import audit_vdata,sha256


def find_step(node,number):
    if hasattr(node,'GetAbsoluteStepNumber') and str(node.GetAbsoluteStepNumber())==str(number) and node.GetVWAFFileName(EAbsolutePath):return node
    if hasattr(node,'GetNumChildren'):
        for index in range(node.GetNumChildren()):
            found=find_step(node.GetChild(index),number)
            if found is not None:return found
    return None


def verify(folder,export_to=None,planes=False):
    folder=Path(folder).resolve();os.chdir(str(folder))
    config=json.loads((folder/'project_manifest.json').read_text(encoding='utf-8'))
    model=Path(config['assembly']);h=config['voxel_size_um']
    doc=VoxelDocument(str(model),h,'um',LOAD)
    if not doc.GetProperties().IsModelBuildComplete():raise RuntimeError('Native model is not marked complete')
    modeler=VoxelModeler(doc);first=find_step(doc.GetModel(),1);final=find_step(doc.GetModel(),config['final_geometry_step'])
    if first is None or final is None:raise RuntimeError('Missing initial/final saved step')
    saved=Path(final.GetVWAFFileName(EAbsolutePath))
    saved_initial=Path(first.GetVWAFFileName(EAbsolutePath))
    watched={str(p):sha256(p) for p in [model,saved_initial,saved]}
    initial=VoxelWafer(modeler);initial.Load(first)
    wafer=VoxelWafer(modeler);wafer.Load(final)
    materials=doc.GetMaterials();si=materials['/Silicon/Si_Xtal'];resist=materials['/Organics/Resist']
    initial_si=float(initial.GetMaterialBounds().VolumeForMaterial([si]))
    final_si=float(wafer.GetMaterialBounds().VolumeForMaterial([si]))
    final_pr=float(wafer.GetMaterialBounds().VolumeForMaterial([resist]))
    resolution=float(wafer.GetResolution())
    samples=[]
    groups=[-24.,-8.,8.,24.] if config['full_layout'] else [24.]
    requested=[(g+offset,kind) for g in groups for offset,kind in [(-3.2,'ridge'),(0.,'ridge'),(3.2,'ridge'),(-1.6,'gap'),(1.6,'gap'),(-6.,'field')]]
    for x,kind in requested:
        point,normal,mat=wafer.GetRayIntersection([x,0.,1.1],[0.,0.,-1.])
        p0,n0,m0=initial.GetRayIntersection([x,0.,1.1],[0.,0.,-1.])
        if mat!=si.GetID() or m0!=si.GetID():raise RuntimeError('Downward air-origin ray did not hit Si')
        samples.append({'x_um':x,'y_um':0.,'kind':kind,'initial_z_um':float(p0[2]),
                        'final_z_um':float(point[2]),'depth_nm':float(p0[2]-point[2])*1000.,
                        'normal':[float(v) for v in normal]})
    checks={'native_build_complete':True,'saved_final_wafer_exists':saved.is_file(),
            'requested_voxel_spacing':abs(resolution-h)<=h*1e-9,
            'positive_remaining_si':final_si>0,'silicon_was_removed':0<final_si<initial_si,
            'no_resist_after_strip':abs(final_pr)<1e-9,
            'all_rays_finite':all(math.isfinite(s['final_z_um']) for s in samples)}
    if config['mode']=='ideal':
        tol=max(h*1000.,.01)
        checks['ideal_ridge_tops_preserved']=all(abs(s['depth_nm'])<=tol for s in samples if s['kind']=='ridge')
        checks['ideal_field_depth_300nm_with_voxel_tolerance']=all(abs(s['depth_nm']-300.)<=tol for s in samples if s['kind']!='ridge')
    else:
        checks['nonideal_ridges_above_field']=min(s['final_z_um'] for s in samples if s['kind']=='ridge')>max(s['final_z_um'] for s in samples if s['kind']!='ridge')
    output=Path(export_to).resolve() if export_to else Path(config['vdata'])
    if export_to and Path(config['vdata']).is_file():
        watched[config['vdata']]=sha256(config['vdata'])
    if export_to:
        if output.exists():raise FileExistsError('Refusing to replace an existing export')
        props=StepProperties('VoxelDataExport');props.outputFileName=str(output)
        props.exportDopants=False;props.exportPlaneEquations=bool(planes)
        wafer.VoxelDataExport(props)
    audit=audit_vdata(output,h,True if (planes if export_to else config['planes']) else None)
    checks['vdata_integrity']=audit['integrity_pass']
    checks['native_sources_unchanged']=all(sha256(p)==digest for p,digest in watched.items())
    report={'schema_version':1,'model':str(model),'final_step':config['final_geometry_step'],'source_saved_wafer':str(saved),
            'mode':config['mode'],'voxel_size_um':resolution,'initial_si_volume_um3':initial_si,
            'final_si_volume_um3':final_si,'removed_si_volume_um3':initial_si-final_si,'final_resist_volume_um3':final_pr,
            'surface_method':'Native downward GetRayIntersection from air, at six flat/central sample positions per simulated group.',
            'surface_samples':samples,'checks':checks,'all_checks_passed':all(checks.values()),
            'vdata':audit,'process_simulation_repeated':False,
            'limit':'Behavioral teaching process. Passing these checks does not calibrate real etch physics or certify arbitrary sidewall/CD accuracy.'}
    path=(output.with_name(output.stem+'_audit.json') if export_to else folder/'native_verification.json')
    path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    if not report['all_checks_passed']:raise RuntimeError('One or more native checks failed: '+str(checks))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--folder',type=Path,required=True)
    p.add_argument('--export-to',type=Path);p.add_argument('--planes',action='store_true');a=p.parse_args()
    try:
        r=verify(a.folder,a.export_to,a.planes);print(json.dumps({'all_checks_passed':True,'vdata':r['vdata']['file'],'final_step':r['final_step']},indent=2));return 0
    except Exception as exc:
        (a.folder/'native_verification_failure.json').write_text(json.dumps({'status':'failed','error':str(exc),'traceback':traceback.format_exc()},indent=2),encoding='utf-8')
        raise

if __name__=='__main__':sys.exit(main())
