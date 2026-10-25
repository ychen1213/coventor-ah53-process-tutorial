"""Generate teaching inputs only. Run with Coventor's Python for gdspy.

No VoxelModeler or process simulation is imported or executed here.
"""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import ideal_generator
import nonideal_generator


def generate(output,install,mode,voxel_nm=20.,planes=False,full_layout=False):
    output=Path(output).resolve();install=Path(install).resolve()
    if not math.isfinite(voxel_nm) or voxel_nm<=0:raise ValueError('voxel_nm must be positive')
    if output.exists() and any(p.name not in ('run_report.json','generate_inputs.log') for p in output.iterdir()):
        raise ValueError('Generator requires a new/empty directory; refusing to replace existing inputs')
    output.mkdir(parents=True,exist_ok=True)
    name='AH53_'+('Ideal' if mode=='ideal' else 'Nonideal')
    base=ideal_generator
    base.ROOT=output;base.INSTALL=install;base.NAME=name
    base.BASE=install/'Examples/Semiconductor/14nmFinFET'
    base.PATTERN=install/'Examples/ProcessStepExamples/PatternDependence'
    if mode=='ideal':base.main()
    else:
        nonideal_generator.ROOT=output;nonideal_generator.INSTALL=install
        nonideal_generator.NAME=name;nonideal_generator.main()
    domain=[-36.,-14.,36.,14.] if full_layout else [16.,-14.,32.,14.]
    lib=base.gdspy.GdsLibrary(infile=str(output/(name+'.gds')))
    cell=lib.cells['AH53_DEMO']
    cell.polygons=[p for p in cell.polygons if 99 not in p.layers]
    cell.add(base.gdspy.Rectangle(tuple(domain[:2]),tuple(domain[2:]),layer=99,datatype=0))
    lib.write_gds(str(output/(name+'.gds')))
    process=ET.parse(str(output/(name+'.vproc')))
    properties=process.getroot().find('___Properties')
    material=properties.find('materialDatabase')
    material_path=(output/(name+'.vmpd')).as_posix()
    material.set('RelativeFileName',material_path);material.set('___text',material_path)
    for step in process.getroot().find('___DocumentTree').findall('___Item'):
        if step.get('___Type')=='VoxelDataExport':
            p=step.find('___Properties')
            p.find('outputFileName').set('___text',(output/(name+'.vdata')).as_posix())
            base.expr(p.find('exportPlaneEquations'),'true' if planes else 'false')
    base.save(process,output/(name+'.vproc'))
    assembly=ET.parse(str(output/(name+'.zam')))
    dp=assembly.find('DocumentProperties')
    dp.find('ModelProperties').set('IsComplete','false')
    dp.find('ModelProperties').set('ModelResolution',format(voxel_nm/1000.,'.17g'))
    dp.find('LayoutFile').set('Filename',(output/(name+'.gds')).as_posix())
    dp.find('ProcessFile').set('Filename',(output/(name+'.vproc')).as_posix())
    dp.find('Output').set('Directory',(output/(name+'-Output')).as_posix()+'/')
    dp.find('ManagerProperties').set('LayerMapFileName',(output/(name+'-layermap.txt')).as_posix())
    stamp=datetime.now().strftime('%A %B %d, %Y')
    for field in ['CreatedOn','LastModified']:dp.find('UserProperties').set(field,stamp)
    base.save(assembly,output/(name+'.zam'))
    params=json.loads((output/'parameters.json').read_text(encoding='utf-8'))
    all_boxes=[[g+o-.8,-10.,g+o+.8,10.] for g in [-24.,-8.,8.,24.] for o in [-3.2,0.,3.2]]
    boxes=[b for b in all_boxes if b[0]>=domain[0] and b[2]<=domain[2]]
    params.update(domain=domain,voxel_size=voxel_nm/1000.,layout_periods=4,simulated_periods=4 if full_layout else 1,
                  protected_ridge_boxes=boxes,export_plane_equations=planes,model_name=name,mode=mode,
                  manifest_only=True,
                  parameter_editing='This file records effective generated inputs. Editing JSON alone does not change GDS/vproc/zam. Use CLI options or edit source/Process editor and rebuild.',
                  model='Simplified AH53 teaching model; not a qualified commercial mark or calibrated fab prediction')
    if mode=='ideal':params['expected_removed_si_volume_um3']=((domain[2]-domain[0])*(domain[3]-domain[1])-len(boxes)*1.6*20.)*.3
    params['interpretation']=['Protected GDS bars remain raised; surrounding silicon is etched.',
        'All GDS context has four groups; DOMAIN controls the actual simulation area.',
        'Input process depths are in um. Native result morphology must be measured.',
        'Nonideal inputs are behavioral assumptions; no chamber chemistry or measured recipe is inferred.',
        'Voxel spacing is a geometric discretization; smaller cells alone do not calibrate process physics.']
    (output/'parameters.json').write_text(json.dumps(params,indent=2,ensure_ascii=False),encoding='utf-8')
    result={'schema_version':1,'mode':mode,'model_name':name,'assembly':str(output/(name+'.zam')),
            'vdata':str(output/(name+'.vdata')),'final_geometry_step':5 if mode=='ideal' else 7,
            'export_step':6 if mode=='ideal' else 8,'voxel_size_um':voxel_nm/1000.,'domain_xy_um':domain,
            'planes':bool(planes),'full_layout':bool(full_layout),'input_files_generated':True,
            'process_simulation_run':False,'parameters_file':str(output/'parameters.json')}
    (output/'project_manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--semulator-root',type=Path,required=True)
    p.add_argument('--mode',choices=['ideal','nonideal'],required=True);p.add_argument('--voxel-nm',type=float,default=20.)
    p.add_argument('--planes',action='store_true');p.add_argument('--full-layout',action='store_true')
    a=p.parse_args();print(json.dumps(generate(a.output,a.semulator_root,a.mode,a.voxel_nm,a.planes,a.full_layout),indent=2))

if __name__=='__main__':main()
