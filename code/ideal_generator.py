"""Create a simplified AH53 teaching example for SEMulator3D 9.3.

The GDS bars are PROTECTED SILICON RIDGES. All surrounding Si is etched.
Run with SEMulator3D's bundled Python (gdspy is already available).
"""
import copy
import json
import os
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET

import gdspy

ROOT = None  # Set by project_generator.py before main().
INSTALL = None
BASE = None
PATTERN = None
NAME = 'AH53_Ideal'


def expr(node, value):
    node.set('___expression', str(value))
    node.attrib.pop('___lastKnownValue', None)


def clone_step(tree, kind, name, source_name=None):
    for item in tree.iter('___Item'):
        if item.get('___Type') == kind and (source_name is None or item.get('___Name') == source_name):
            step = copy.deepcopy(item)
            step.set('UUID', str(uuid.uuid4()))
            step.set('___Name', name)
            step.set('isExpanded', 'true')
            step.attrib.pop('stepDisabled', None)
            props = step.find('___Properties')
            props.find('stepName').set('___text', name)
            return step, props
    raise ValueError(kind)


def material(node, path):
    for child in list(node):
        node.remove(child)
    group, name = path.strip('/').split('/')
    return ET.SubElement(node, '_MaterialNodeType_' + group + '_MaterialLeafType_' + name,
                         {'UserDefinedName': path, 'isEnable': 'true'})


def save(tree, path):
    tree.write(str(path), encoding='utf-8', xml_declaration=True)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    lib = gdspy.GdsLibrary(unit=1e-6, precision=1e-9)
    cell = lib.new_cell('AH53_DEMO')
    bars = []
    for period_center in [-24.0, -8.0, 8.0, 24.0]:
        for offset in [-3.2, 0.0, 3.2]:
            x = period_center + offset
            cell.add(gdspy.Rectangle((x - 0.8, -10), (x + 0.8, 10), layer=1, datatype=0))
            bars.append([x - 0.8, -10, x + 0.8, 10])
    cell.add(gdspy.Rectangle((-36, -14), (36, 14), layer=99, datatype=0))
    lib.write_gds(str(ROOT / (NAME + '.gds')))
    (ROOT / (NAME + '-layermap.txt')).write_text('AH53_KEEP  1  0\nDOMAIN  99  0\n', encoding='ascii')

    base = ET.parse(str(BASE / '14nmFinFET.vproc'))
    pattern = ET.parse(str(PATTERN / 'array_trench.vproc'))
    proc = copy.deepcopy(pattern)
    root = proc.getroot()
    props = root.find('___Properties')
    props.find('modelUnit').set('___activeMember', 'um')
    matfile = props.find('materialDatabase')
    matfile.set('RelativeFileName', './' + NAME + '.vmpd')
    matfile.set('___text', (ROOT / (NAME + '.vmpd')).as_posix())
    parser = root.find('___Parser')
    for child in list(parser):
        parser.remove(child)
    tree = root.find('___DocumentTree')
    for child in list(tree):
        if child.tag != '___Properties':
            tree.remove(child)

    step, p = clone_step(pattern, 'WaferSetup', '01 Si substrate 1um')
    expr(p.find('thickness'), 1)
    p.find('waferBounds/type/mask/name').set('___text', 'DOMAIN')
    tree.append(step)

    step, p = clone_step(base, 'Deposit', '02 Coat resist 0.5um', 'DEP MandRes')
    for mask_name in p.findall('.//mask/name'):
        mask_name.set('___text', '')
    expr(p.find('thickness'), 0.5)
    material(p.find('material'), '/Organics/Resist')
    p.find('type').set('___activeMember', 'planarizing ')
    p.find('type/planarizing/referencePlane').set('___activeMember', 'highest')
    p.find('stepAction').set('___text', 'Planarizing Deposit')
    p.find('stepAction').set('icon', ':/icons/Deposit_planarizing')
    tree.append(step)

    step, p = clone_step(base, 'ExposeMaterial', '03 Protect AH53 ridges')
    expr(p.find('thickness'), 0)
    p.find('mask/name').set('___text', 'AH53_KEEP')
    expr(p.find('mask/polarity'), 'true')  # Light: remove resist OUTSIDE drawn shapes.
    p.find('lithography/lithographyEmulation').set('isEnable', 'false')
    expr(p.find('lithography/lithographyEmulation/sizeThreshold'), 0)
    tree.append(step)

    step, p = clone_step(pattern, 'Etch', '04 Etch surrounding Si 300nm')
    expr(p.find('depth'), 0.3)
    si = material(p.find('materials'), '/Silicon/Si_Xtal')
    ET.SubElement(si, 'etchRatio', {'___expression': '1'})
    ET.SubElement(si, 'replacementMaterial', {'VersionNumber': '9.2.0.0', 'uiHideChildNodes': 'true', 'uiUseCustomMaterialWidget': 'true'})
    expr(p.find('selectivity'), 'false')
    p.find('type').set('___activeMember', 'straight ')
    p.find('type/straight/advanced').set('isEnable', 'false')
    p.find('type/straight/advanced/mask/name').set('___text', '')
    tree.append(step)

    step, p = clone_step(base, 'RemoveMaterials', '05 Strip resist')
    material(p.find('materials'), '/Organics/Resist')
    tree.append(step)

    export_example = ET.parse(str(INSTALL / 'Examples/Python/VDataPythonIO/layerEtchComparison_manyLayer.vproc'))
    step, p = clone_step(export_example, 'VoxelDataExport', '06 Export final VDATA')
    p.find('wafer').set('___text', 'Wafer1')
    p.find('outputFileName').set('___text', (ROOT / (NAME + '.vdata')).as_posix())
    expr(p.find('exportDopants'), 'false')
    expr(p.find('exportPlaneEquations'), 'false')
    tree.append(step)
    save(proc, ROOT / (NAME + '.vproc'))

    mats = ET.parse(str(BASE / '14nmFinFET.vmpd'))
    for item in mats.iter('___Item'):
        if item.get('___Type') == 'Material' and item.get('___Name') == 'Si_Xtal':
            color = item.find('___Properties/visualProperties/color')
            color.set('___red', '108')
            color.set('___green', '153')
            color.set('___blue', '190')
    save(mats, ROOT / (NAME + '.vmpd'))

    zam = ET.parse(str(INSTALL / 'Examples/ProcessStepExamples/DRIE_Loop/DRIE_Loop.zam'))
    dp = zam.getroot().find('DocumentProperties')
    dp.find('ModelProperties').set('ModelResolution', '0.02')
    dp.find('LayoutFile').set('Filename', NAME + '.gds')
    dp.find('LayoutFile').set('TopCell', 'AH53_DEMO')
    dp.find('ProcessFile').set('Filename', NAME + '.vproc')
    dp.find('Output').set('Directory', NAME + '-Output/')
    dp.find('ManagerProperties').set('LayerMapFileName', NAME + '-layermap.txt')
    dp.find('ManagerProperties').set('RunType', 'Start From Blank')
    dp.find('ManagerProperties').set('StartViewer', 'false')
    dp.find('ModelArea').set('BoundingMask', 'DOMAIN')
    dp.find('UserProperties').set('Author', '')
    dp.find('UserProperties').set('Comments', 'Simplified AH53 teaching model; GDS stripes are protected Si ridges; surroundings etched 300nm. Corrected polarity: Light.')
    dp.find('UserProperties').set('CreatedOn', 'Saturday October 24, 2026')
    dp.find('UserProperties').set('LastModified', 'Saturday October 24, 2026')
    dp.find('UserProperties').set('Revision', '1')
    save(zam, ROOT / (NAME + '.zam'))

    params = dict(model='Simplified single-direction AH53 teaching example, not a qualified commercial mark',
                  units='um', material='Si_Xtal', substrate_thickness=1.0,
                  resist_thickness=0.5, etch_depth=0.3, voxel_size=0.02,
                  pitch=16.0, line_width=1.6, subpitch=3.2, periods=4,
                  line_length=20.0, gds_bars_mean='protected Si ridges; etch all surrounding Si',
                  mask_polarity='Light (true): expose/remove resist outside GDS polygons',
                  layout_cell='AH53_DEMO', protected_layer=[1, 0], domain_layer=[99, 0],
                  domain=[-36, -14, 36, 14], protected_ridge_boxes=bars,
                  expected_removed_si_volume_um3=(72*28-12*1.6*20)*0.3,
                  geometry_reference='Simplified three-bar-per-group teaching layout; not a qualified commercial mark')
    (ROOT / 'parameters.json').write_text(json.dumps(params, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Created:', ROOT)
    print('12 PROTECTED Si ridges, surroundings etched 0.3um; P=16um, CD=1.6um, voxel=0.02um')


if __name__ == '__main__':
    raise SystemExit('Use project_generator.py; an explicit new output is required.')
