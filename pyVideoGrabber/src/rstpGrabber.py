#!/usr/bin/python
# -*- coding: utf-8 -*-


import rtsp
import threading
import io
import base64
import asyncio
import os
import logging
import time
import json
import sys
from datetime import datetime

if 'LOGLEVEL' in os.environ:
    loglevel = os.environ['LOGLEVEL']
else:
    loglevel=logging.DEBUG
    
logging.basicConfig(level=loglevel)
logger = logging.getLogger("rtspGrabber")


class RTSP_grabber(threading.Thread):
    def __init__(self, settings, callback, event_loop):
        threading.Thread.__init__(self)
        self.isRunning = True
        self.stream_uri = settings['streamURI']
        self.client = rtsp.Client(rtsp_server_uri=self.stream_uri, verbose=True)
        self.cameraId = settings['cameraId']
        self.location_name = settings['locationName']
        self.fps = settings['FPS']
        self.callback = callback
        self.loop = event_loop
        logger.info("RTSP stream initialized for camera %s at %s" % (self.cameraId, self.location_name))

    def image_encoder(self, img):
        if img.width > 720:
            factor = 720/img.width
            newWidth = int(img.width * factor)
            if newWidth % 2 != 0:
                newWidth = newWidth + 1
            newHeight = int(img.height * factor)
            if newHeight % 2 != 0:
                newHeight = newHeight + 1
            newSize = (newWidth, newHeight)
            img = img.resize(newSize)
        bytes = io.BytesIO()
        img.save(bytes, format="JPEG")
        bytes.seek(0)
        return base64.b64encode(bytes.read()).decode('ascii')    

    def run(self):
        asyncio.set_event_loop(self.loop)
        last_ts = time.time()-1
        fps = 1 / self.fps
        while self.is_alive() and self.isRunning:
            frame = self.client.read()
            if not frame is None and self.client.isOpened():
                new_ts = time.time()
                if new_ts - last_ts >= fps :
                    last_ts = new_ts
                    key = self.location_name + "_" + self.cameraId
                    b64frame = self.image_encoder(frame)
                    timestamp = datetime.utcnow().isoformat(timespec='milliseconds') + "Z"
                    message = {
                        "timestamp":timestamp,
                        "cameraId":self.cameraId,
                        "locationName":self.location_name,
                        "image":b64frame
                    }
                    asyncio.run_coroutine_threadsafe(self.callback(json.dumps(message), key), self.loop)
            elif not self.client.isOpened():
                logger.warning("Stream from camera %s at %s got disconnected. Attempting reconnection" % (self.cameraId, self.location_name))
                self.client.close()
                self.client.open()
                timeout=0
                while not self.client.isOpened() and timeout<10:
                    time.sleep(1)
                    timeout = timeout +1
                if not self.client.isOpened():
                    logger.error("Client didn't get reconnected. Resetting instance")
                    self.client = rtsp.Client(rtsp_server_uri=self.stream_uri, verbose=True)
            else:
                logger.warning("Stream from camera %s at %s is not transmitting" % (self.cameraId, self.location_name))
                time.sleep(5)
    
    def stop(self):
        self.isRunning = False
        
