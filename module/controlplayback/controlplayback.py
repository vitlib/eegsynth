#!/usr/bin/env python

import time
import ConfigParser # this is version 2.x specific, on version 3.x it is called "configparser" and has a different API
import redis
import sys
import os
import edflib
import numpy as np
import datetime
import time

if hasattr(sys, 'frozen'):
    basis = sys.executable
elif sys.argv[0]!='':
    basis = sys.argv[0]
else:
    basis = './'
installed_folder = os.path.split(basis)[0]

# eegsynth/lib contains shared modules
sys.path.insert(0, os.path.join(installed_folder,'../../lib'))
import EEGsynth
import EDF

config = ConfigParser.ConfigParser()
config.read(os.path.join(installed_folder, 'controlplayback.ini'))

# this determines how much debugging information gets printed
debug = config.getint('general','debug')

try:
    r = redis.StrictRedis(host=config.get('redis','hostname'), port=config.getint('redis','port'), db=0)
    response = r.client_list()
    if debug>0:
        print "Connected to redis server"
except redis.ConnectionError:
    print "Error: cannot connect to redis server"
    exit()

f = EDF.EDFReader()
f.open(config.get('playback', 'file'))

if debug>1:
    print "NSignals", f.getNSignals()
    print "SignalFreqs", f.getSignalFreqs()
    print "NSamples", f.getNSamples()

channels = f.getSignalTextLabels()
channelz = f.getSignalTextLabels()

fSample = f.getSignalFreqs()[0]
nSamples = f.getNSamples()[0]

# search-and-replace to reduce the length of the channel labels
for replace in config.items('replace'):
    print replace
    for i in range(len(channelz)):
        channelz[i] = channelz[i].replace(replace[0], replace[1])
for s,z in zip(channels, channelz):
    print "Writing channel", s, "as control value", z

for chanindx in range(f.getNSignals()):
    if f.getSignalFreqs()[chanindx]!=f.getSignalFreqs()[0]:
        raise IOError('unequal SignalFreqs')
    if f.getNSamples()[chanindx]!=f.getNSamples()[0]:
        raise IOError('unequal NSamples')

block     = 0
blocksize = 1
begsample = 0
endsample = 0
adjust    = 1

while True:
    if endsample>nSamples-1:
        if debug>0:
            print "End of file reached, jumping back to start"
        begsample = 0
        endsample = 0
        continue

    if EEGsynth.getint('playback', 'rewind', config, r):
        if debug>0:
            print "Rewind pressed, jumping back to start of file"
        begsample = 0
        endsample = 0

    if not EEGsynth.getint('playback', 'play', config, r):
        if debug>0:
            print "Paused"
        time.sleep(0.1);
        continue

    # measure the time that it takes
    now = time.time()

    if debug>1:
        print "Playing control value", block

    for i,chan in enumerate(channelz):
        key = chan
        val = f.readSamples(chanindx, begsample, endsample)
        r.set(key,val)

    # this approximates the real time streaming speed
    desired = blocksize/(fSample*EEGsynth.getfloat('playback', 'speed', config, r))
    # the adjust factor compensates for the time spent on reading and writing the data
    time.sleep(adjust * desired);

    begsample += blocksize
    endsample += blocksize
    block += 1

    elapsed = time.time() - now
    # adjust the relative delay for the next iteration
    # the adjustment factor should only change a little per iteration
    adjust = 0.1 * desired/elapsed + 0.9 * adjust