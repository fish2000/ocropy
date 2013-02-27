#!/usr/bin/env python

import sys, time, urllib, traceback, glob, os, os.path

assert sys.version_info[0]==2 and sys.version_info[1]>=7,\
    "you must install and use OCRopus with Python version 2.7 or later, but not Python 3.x"

from distutils.core import setup, Extension, Command
from distutils.command.install_data import install_data

from ocrolib import default
modeldir = "models/"
modelfiles = default.installable
modelprefix = "http://iupr1.cs.uni-kl.de/~tmb/ocropus-models/"

class DownloadCommand(Command):
    description = "Download OCRopus datafiles. (This needs to happen prior to installation.)"
    user_options = []
    def initialize_options(self): pass
    def finalize_options(self): pass
    def run(self):
        print "Starting download of about 500Mbytes of model data."
        time.sleep(3) # give them time to quit
        for m in modelfiles:
            dest = modeldir+m
            if os.path.exists(dest):
                print m,": already downloaded"
                continue
            url = modelprefix+m+".bz2"
            cmd = "curl '%s' | bunzip2 > '%s.temp' && mv '%s.temp' '%s'"%(url,dest,dest,dest)
            print "\n#",cmd,"\n"
            if os.system(cmd)!=0:
                print "download failed"
                sys.exit(1)

setup(
        name='ocropy',
        version='0.6',
        author="Thomas Breuel",
        description="The core of the OCRopus OCR system.",
        
        packages=["ocrolib"],
        data_files=[
            ('share/ocropus', glob.glob("*.glade")),
            ('share/ocropus', [modeldir+m for m in modelfiles]),
            ('share/ocropus', glob.glob("models/*.lnorm")),
            ('share/ocropus', ["models/gradient.lineest"])],
        
        scripts=[c for c in glob.glob("ocropus-*") if "." not in c and "~" not in c],
        cmdclass={ "download_models": DownloadCommand, },
        
        install_requires=[
            'numpy', 'scipy', 'tables',
            'PIL'],
     )
