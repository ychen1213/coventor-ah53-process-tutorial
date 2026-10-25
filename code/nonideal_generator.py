"""Uncalibrated nonideal process demonstration using native SEMulator3D steps.

Keeps the original ideal project unchanged. Parameters below are illustrative
behavioral inputs, not inferred chamber settings or measured process data.
"""
import copy
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = None
NAME = 'AH53_Nonideal'
INSTALL = None
IDEAL = None  # Optional provenance reference only.
import ideal_generator as base


def expr(parent, path, value):
    n = parent.find(path)
    if n is None:
        raise KeyError(path)
    n.set('___expression', str(value).lower() if isinstance(value, bool) else str(value))
    n.attrib.pop('___lastKnownValue', None)
    n.attrib.pop('readonly', None)


def enabled(n, state=True):
    n.set('isEnable', 'true' if state else 'false')
    if state:
        for c in n.iter():
            c.attrib.pop('readonly', None)


def set_name(step, name):
    step.set('___Name', name)
    step.find('___Properties/stepName').set('___text', name)


def multi_step(template, name, depth, mode):
    step, p = base.clone_step(template, 'MultiEtch', name, 'Multi Etch3')
    step.set('Comment', 'Uncalibrated illustrative input; inspect measured morphology after building.')
    expr(p, 'depth', depth)
    mats = p.find('materials')
    for m in list(mats):
        if m.get('UserDefinedName') not in ('/Silicon/Si_Xtal', '/Organics/'):
            mats.remove(m)
    si = next(m for m in mats if m.get('UserDefinedName') == '/Silicon/Si_Xtal')
    pr = next(m for m in mats if m.get('UserDefinedName') == '/Organics/')
    expr(si, 'etchRatio', 1)
    expr(si, 'lateralRatio', 0.15 if mode == 'taper' else 0.1)
    si.find('etchType').set('___activeMember', mode + ' ')
    expr(si, 'etchType/taper/sidewallAngle', 10)
    expr(pr, 'etchRatio', 0.25 if mode == 'taper' else 0.1)
    expr(pr, 'lateralRatio', 0.05)
    pr.find('etchType').set('___activeMember', 'sputter ' if mode == 'taper' else 'basic ')
    expr(pr, 'etchType/sputter/sputterRatio', 0.5)
    expr(pr, 'etchType/sputter/maxYieldAngle', 50)
    for pdparam in pr.findall('.//patternDependence/*'):
        pdparam.set('___activeMember', 'disable ')
    p.find('sourceProperties/waferTiltAndTwist').set('___activeMember', 'fixed ')
    expr(p, 'sourceProperties/visibilitySourceSigma', 0.12)
    expr(p, 'sourceProperties/waferTiltAndTwist/fixed/tilt', 0 if mode == 'taper' else 20)
    expr(p, 'sourceProperties/waferTiltAndTwist/fixed/twist', 0)
    enabled(p.find('advanced'))
    expr(p, 'advanced/acceleration', 0)
    enabled(p.find('patternDependenceWrapper'), mode == 'taper')
    pd = p.find('patternDependenceWrapper/patternDependence')
    pd.find('globalMask/name').set('___text', 'AH53_KEEP')
    expr(pd, 'globalMask/polarity', True)
    expr(pd, 'globalMask/lithographyResolution', 0)
    pd.find('localMask').set('___activeMember', 'useGlobal ')
    enabled(pd.find('advanced'), mode == 'taper')
    enabled(pd.find('advanced/depth'), mode == 'taper')
    for key, value in [('constant', 0.6), ('coefficient1', 0.4), ('radius1', 3.2),
                       ('directed1', False), ('coefficient2', 0), ('radius2', 1),
                       ('directed2', False), ('averaging', False)]:
        expr(pd, 'advanced/depth/' + key, value)
    return step


def main():
    base.main()
    # Keep the full mask context, but simulate one complete three-bar period.
    layout_path = ROOT / (NAME + '.gds')
    lib = base.gdspy.GdsLibrary(infile=str(layout_path))
    cell = lib.cells['AH53_DEMO']
    cell.polygons = [p for p in cell.polygons if 99 not in p.layers]
    cell.add(base.gdspy.Rectangle((16, -14), (32, 14), layer=99, datatype=0))
    lib.write_gds(str(layout_path))
    proc_path = ROOT / (NAME + '.vproc')
    tree = ET.parse(str(proc_path))
    flow = tree.getroot().find('___DocumentTree')
    original = flow.findall('___Item')
    litho = original[2].find('___Properties')
    set_name(original[2], '03 Rounded rough resist pattern')
    enabled(litho.find('lithography/lithographyEmulation'))
    expr(litho, 'lithography/lithographyEmulation/sizeThreshold', 0.12)
    noise = litho.find('lithography/edgeNoise')
    enabled(noise)
    noise.find('noiseType').set('___activeMember', 'gaussian')
    expr(noise, 'rmsAmplitude', 0.06)
    expr(noise, 'corrLength', 0.5)
    enabled(noise.find('advancedOptions'))
    expr(noise, 'advancedOptions/seed', 53)
    original[2].set('Comment', 'Lithographic corner transfer and PR edge noise: threshold 120nm, RMS 60nm, correlation 500nm, seed53. These are assumed inputs, not measured Si LER.')

    template = ET.parse(str(INSTALL / 'Examples/Semiconductor/STI/STI_MultiEtch.vproc'))
    main_etch = multi_step(template, '04 Taper etch with density loading', 0.22, 'taper')
    directional = multi_step(template, '05 Tilted directional trim', 0.04, 'visibility')
    finish = copy.deepcopy(original[3])
    set_name(finish, '06 Isotropic Si finish under resist')
    p = finish.find('___Properties')
    expr(p, 'depth', 0.04)
    p.find('type').set('___activeMember', 'basic ')
    p.find('stepAction').set('___text', 'Enhanced Basic Etch')
    p.find('stepAction').set('icon', ':/icons/Etch_basic')
    expr(p, 'type/basic/lateralRatio', 1)
    p.find('type/basic/patternDependenceWrapper').set('___activeMember', 'none ')
    finish.set('Comment', '40nm isotropic component with resist still present; models lateral attack and curved transitions. Does not impose a measured corner radius.')
    strip, export = original[4], original[5]
    set_name(strip, '07 Strip resist - final nonideal Si')
    set_name(export, '08 Export nonideal VDATA')
    for n in original:
        flow.remove(n)
    for n in original[:3] + [main_etch, directional, finish, strip, export]:
        flow.append(n)
    base.save(tree, proc_path)

    zam_path = ROOT / (NAME + '.zam')
    zam = ET.parse(str(zam_path))
    zam.find('DocumentProperties/UserProperties').set('Comments',
        'Uncalibrated nonideal AH53 process demonstration. Protected raised Si bars. Rough lithography, taper and mask erosion, pattern-dependent depth, tilted visibility trim, isotropic finish. Nominal sum 300nm; local final depth is measured, not constrained.')
    base.save(zam, zam_path)
    parameters = json.loads((ROOT / 'parameters.json').read_text(encoding='utf-8'))
    parameters.pop('expected_removed_si_volume_um3', None)
    parameters['domain'] = [16, -14, 32, 14]
    parameters['layout_periods'] = 4
    parameters['simulated_periods'] = 1
    parameters['protected_ridge_boxes'] = [b for b in parameters['protected_ridge_boxes'] if b[0] >= 16 and b[2] <= 32]
    parameters.update({'model': 'Uncalibrated nonideal process demonstration; NOT a fab-recipe prediction',
        'ideal_reference': None,
        'input_assumptions': {
            'lithography_size_threshold_um': 0.12,
            'resist_edge_noise_rms_um': 0.06, 'correlation_length_um': 0.5, 'random_seed': 53,
            'main_taper_etch_depth_um': 0.22, 'taper_angle_degrees_from_vertical': 10,
            'main_si_lateral_ratio': 0.15,
            'main_pr_relative_etch_rate': 0.25, 'pr_sputter_ratio': 0.5,
            'pr_sputter_max_yield_angle_degrees': 50,
            'depth_loading_factor': '0.6 + 0.4 * Gaussian(open_mask, radius=3.2um)',
            'depth_loading_feature_averaging': False,
            'directional_trim_nominal_depth_um': 0.04, 'source_tilt_degrees': 20,
            'source_twist_degrees': 0, 'visibility_source_sigma_radians': 0.12,
            'directional_si_lateral_ratio': 0.1,
            'isotropic_finish_depth_um': 0.04, 'isotropic_finish_lateral_ratio': 1,
            'nominal_depth_sum_um': 0.3},
        'interpretation': [
            'One complete three-bar period is simulated in a 16um by 28um window; the GDS retains the four-period layout.',
            '300nm is nominal sum; local floor depth and final raised height are output quantities.',
            '10 degrees is an input relative to vertical, not a guaranteed final sidewall angle.',
            'LER input belongs to patterned resist; final silicon roughness is measured separately.',
            'Depth loading coefficients illustrate sensitivity; they are not calibrated experimental coefficients.',
            '20nm grid limits characterization of small corner radii; no sub-grid accuracy claimed.',
            'The three etch components describe a hypothetical multi-stage process, not an equipment chemistry recipe.']})
    (ROOT / 'parameters.json').write_text(json.dumps(parameters, indent=2), encoding='utf-8')
    print('Created native 8-step nonideal project:', zam_path)


if __name__ == '__main__':
    raise SystemExit('Use project_generator.py; an explicit new output is required.')
