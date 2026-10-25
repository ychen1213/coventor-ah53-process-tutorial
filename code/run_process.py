"""One teaching process run: generate inputs, explicitly build, audit or export.

The controller uses only the standard library. Native work runs in Coventor's
own Python/executable, in a new ASCII directory. No existing teaching project
or FDTD session is modified.
"""
import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from vdata_io import audit_vdata,sha256

CODE=Path(__file__).resolve().parent
TUTORIAL=CODE.parent


def write_json(path,value):
    path=Path(path);tmp=path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8');os.replace(str(tmp),str(path))


def ascii_path(path):
    path=Path(path).expanduser().resolve()
    try:str(path).encode('ascii')
    except UnicodeEncodeError:raise ValueError('Use an ASCII output path for the SEMulator3D 9.3 file APIs')
    return path


def discover(explicit=None):
    choices=[Path(explicit)] if explicit else []
    if not explicit:
        choices += [Path(os.environ[n]) for n in ['SEMULATOR_ROOT','MEMULATOR_ROOT'] if os.environ.get(n)]
        choices += [Path('D:/SEMulator3D9'),Path('C:/Coventor/SEMulator3D9')]
        for env in ['ProgramFiles','ProgramW6432']:
            if os.environ.get(env):choices += list(Path(os.environ[env]).glob('Coventor/SEMulator3D*'))
    for root in choices:
        python=root/'runtime/python/v3.6/NT40_x64/python.exe'
        builder=root/'bin/NT40_x64/ModelBuilder.exe'
        if python.is_file() and builder.is_file():return root.resolve(),python.resolve(),builder.resolve()
    raise ValueError('SEMulator3D 9.3 with bundled Python 3.6 was not found; use --semulator-root')


def native_env(root,python,folder):
    env=os.environ.copy()
    for name in ['PYTHONHOME','PYTHON_DOM','PYTHONSTARTUP','PYTHONCASEOK']:env.pop(name,None)
    env.update(MEMULATOR_ROOT=str(root),MTI_ROOT=str(root),MEMULATOR_PROJECTDIR=str(folder),
               MTI_ARCH='NT40_x64',MTI_PRODUCTNAME='SEMulator3D',PYTHONDONTWRITEBYTECODE='1',
               PYTHONLEGACYWINDOWSSTDIO='1',PYTHONIOENCODING='utf-8',VDATA_CONVERTER_API_VERSION='9.3')
    env['PYTHONPATH']=os.pathsep.join(str(p) for p in [CODE,root/'runtime/pyc',root/'bin/NT40_x64',root/'apps/contrib/py'])
    env['PATH']=os.pathsep.join([str(root/'bin/NT40_x64'),str(root/'bin'),str(python.parent),str(python.parent/'DLLs'),env.get('PATH','')])
    env['TCL_LIBRARY']=str(python.parent/'tcl/tcl8.4');env['TK_LIBRARY']=str(python.parent/'tcl/tk8.4')
    if not env.get('LM_LICENSE_FILE') and (root/'license/license.lic').is_file():env['LM_LICENSE_FILE']=str(root/'license/license.lic')
    return env


def run_stage(command,folder,env,label,report):
    log=folder/(label+'.log');start=time.monotonic()
    entry={'name':label,'command':[str(v) for v in command],'log':str(log),'status':'running'}
    report_path=Path(report.get('report_path',str(folder/'run_report.json')))
    report['stages'].append(entry);write_json(report_path,report)
    print('START '+label+'; log: '+str(log),flush=True)
    with log.open('wb') as stream:
        process=subprocess.Popen([str(v) for v in command],cwd=str(folder),env=env,stdout=stream,
                                 stderr=subprocess.STDOUT,shell=False,
                                 creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        entry['pid']=process.pid;last=start
        try:
            while process.poll() is None:
                try:process.wait(timeout=1.)
                except subprocess.TimeoutExpired:pass
                if time.monotonic()-last>=30:
                    print(label+' still running, %.0f seconds; see %s'%(time.monotonic()-start,log),flush=True);last=time.monotonic()
        except KeyboardInterrupt:
            # ModelBuilder documents --killFile; only its own per-run file is touched.
            if label=='build':
                (folder/'cancel_modelbuild.request').write_text('cancel requested by controller',encoding='ascii')
                entry.update(status='cancellation_requested',elapsed_seconds=time.monotonic()-start)
                write_json(report_path,report)
                print('Cancellation requested for this model build; waiting for native shutdown.',flush=True)
                process.wait(timeout=120)
            else:
                process.terminate();process.wait(timeout=30)
            raise
    entry.update(returncode=process.returncode,elapsed_seconds=time.monotonic()-start,
                 status='complete' if process.returncode==0 else 'failed')
    write_json(report_path,report)
    if process.returncode:raise RuntimeError(label+' failed (exit '+str(process.returncode)+'); inspect '+str(log))
    print('DONE '+label+' in %.2f s'%entry['elapsed_seconds'],flush=True)


def main(argv=None):
    controller_start=time.monotonic()
    p=argparse.ArgumentParser(description=__doc__)
    action=p.add_mutually_exclusive_group()
    action.add_argument('--generate-only',action='store_true',help='Write inputs only; default action')
    action.add_argument('--run',action='store_true',help='Generate and perform actual native process simulation')
    action.add_argument('--export-only',action='store_true',help='Export a completed own run under a new file name, without rebuilding')
    action.add_argument('--check-only',action='store_true',help='Pure standard-library VDATA integrity audit, no SDK')
    p.add_argument('--mode',choices=['ideal','nonideal'],help='Default ideal for a new run')
    p.add_argument('--output',type=Path,help='New/empty ASCII folder; existing own folder only with --resume/export/check')
    p.add_argument('--semulator-root',type=Path);p.add_argument('--voxel-nm',type=float,help='New model spacing; default 20 nm')
    p.add_argument('--planes',action='store_true',help='Export native per-voxel interface plane equations; larger file')
    p.add_argument('--full-layout',action='store_true',help='Simulate all four groups; default one complete group')
    p.add_argument('--resume',action='store_true',help='With --run, incrementally build an existing own run; do not regenerate inputs')
    p.add_argument('--vdata',type=Path,help='Existing file for --check-only')
    args=p.parse_args(argv)
    if args.voxel_nm is not None and (not math.isfinite(args.voxel_nm) or args.voxel_nm<=0):p.error('--voxel-nm must be finite and positive')
    if args.resume and not args.run:p.error('--resume requires --run')
    report=None;folder=None
    try:
        if args.check_only:
            if args.vdata:path=args.vdata.resolve()
            elif args.output:
                config=json.loads((args.output/'project_manifest.json').read_text(encoding='utf-8'));path=Path(config['vdata'])
            else:raise ValueError('--check-only requires --vdata FILE or --output an existing run')
            result=audit_vdata(path)
            dest=path.with_name(path.stem+'_integrity.json');write_json(dest,result)
            print(json.dumps({'integrity_pass':True,'report':str(dest),'vdata':str(path)},indent=2));return 0
        mode=args.mode or 'ideal'
        folder=ascii_path(args.output or TUTORIAL/'runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+mode))
        if args.export_only or args.resume:
            config=json.loads((folder/'project_manifest.json').read_text(encoding='utf-8'))
            if Path(config['assembly']).resolve().parent!=folder:raise ValueError('Run manifest points outside this output folder')
            if args.mode and args.mode!=config['mode']:raise ValueError('Mode differs from saved run')
            if args.voxel_nm is not None and abs(args.voxel_nm/1000.-config['voxel_size_um'])>1e-12:raise ValueError('Changing spacing needs a new output, not resume/export')
            if args.full_layout and not config['full_layout']:raise ValueError('Changing area needs a new run')
        else:
            if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):raise ValueError('Refusing a nonempty output folder; choose a new one')
            folder.mkdir(parents=True,exist_ok=True)
            config=None
        root,python,builder=discover(args.semulator_root);env=native_env(root,python,folder)
        report={'schema_version':1,'status':'starting','action':'export_only' if args.export_only else ('run' if args.run else 'generate_only'),
                'output':str(folder),'semulator_root':str(root),'sdk_python':str(python),'stages':[],
                'native_process_build_run':False,'optical_fdtd_simulation_run':False,
                'license_handling':'Inherited license environment; fallback is installation license path. License contents are never read.'}
        if args.export_only:
            export_stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            (folder/'exports').mkdir(exist_ok=True)
            report['report_path']=str(folder/'exports'/('export_report_'+export_stamp+'.json'))
        else:report['report_path']=str(folder/'run_report.json')
        write_json(report['report_path'],report)
        if args.export_only:
            target_dir=folder/'exports';target_dir.mkdir(exist_ok=True)
            target=target_dir/(config['model_name']+'_'+export_stamp+'.vdata')
            cmd=[python,CODE/'native_verify.py','--folder',folder,'--export-to',target]
            if args.planes:cmd.append('--planes')
            run_stage(cmd,folder,env,'export_saved_geometry_'+export_stamp,report)
            report.update(status='export_complete',export_vdata=str(target),native_process_build_run=False)
        else:
            if not args.resume:
                cmd=[python,CODE/'project_generator.py','--output',folder,'--semulator-root',root,'--mode',mode,'--voxel-nm',str(args.voxel_nm or 20.)]
                if args.planes:cmd.append('--planes')
                if args.full_layout:cmd.append('--full-layout')
                run_stage(cmd,folder,env,'generate_inputs',report)
                config=json.loads((folder/'project_manifest.json').read_text(encoding='utf-8'))
            elif args.planes and not config['planes']:raise ValueError('Resume does not alter the export step; use --export-only --planes or a new run')
            if args.run:
                cancel_request=folder/'cancel_modelbuild.request'
                if cancel_request.is_file():cancel_request.unlink()
                cmd=[builder,'-m',config['assembly'],'--killFile',folder/'cancel_modelbuild.request']
                if args.resume:cmd.append('-i')
                report['native_process_build_run']=True
                report['native_process_build_completed']=False
                run_stage(cmd,folder,env,'build',report)
                model=ET.parse(config['assembly'])
                if model.find('DocumentProperties/ModelProperties').get('IsComplete','').lower()!='true':raise RuntimeError('Builder exited but assembly is not complete')
                build_log=(folder/'build.log').read_text(encoding='utf-8',errors='replace')
                if 'Build process completed' not in build_log:raise RuntimeError('No successful build marker in log')
                report['native_process_build_completed']=True
                run_stage([python,CODE/'native_verify.py','--folder',folder],folder,env,'verify_saved_geometry',report)
                verification=json.loads((folder/'native_verification.json').read_text(encoding='utf-8'))
                if not verification.get('all_checks_passed'):raise RuntimeError('Native geometry or VDATA audit failed')
                report.update(status='complete',vdata=config['vdata'],native_verification=str(folder/'native_verification.json'))
            else:report.update(status='inputs_generated',native_process_build_run=False,assembly=config['assembly'])
        report['controller_elapsed_seconds']=time.monotonic()-controller_start
        report['measured_stage_wall_seconds_sum']=sum(s.get('elapsed_seconds',0.) for s in report['stages'])
        write_json(report['report_path'],report)
        print(json.dumps({'status':report['status'],'output':str(folder),'report':report['report_path']},indent=2));return 0
    except BaseException as exc:
        if isinstance(exc,SystemExit):raise
        if report is not None:
            report.update(status='failed',error=str(exc),traceback=traceback.format_exc(),controller_elapsed_seconds=time.monotonic()-controller_start);write_json(report['report_path'],report)
        print('ERROR: '+str(exc),file=sys.stderr);return 1

if __name__=='__main__':sys.exit(main())
