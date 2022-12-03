import sys
import warnings
from timeit import default_timer as timer
from datetime import datetime
import progressbar
import asyncio
import pyshark
import os
import re

# test github

class VoipRecorder:

    def __init__(self, filename):
 
        self.active_call = False    
    
        # seznamy pro rtp payloady
        self.rtp_list_1 =[]
        self.rtp_list_2 =[]
    
        # soubory pro raw audio
        self.raw_audio_1 = None
        self.raw_audio_2 = None
        
        self.lastRtpReceived = timer()

        self.first_ssrc = 0
        
        self.from_tag = ""
        self.to_tag = ""

        self.from_rdy = False
        self.to_rdy = False

        self.stream_rdy = False
        self.filename = filename

    def process_recording(self):
        rec_time = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")

        # write raw audio packets to files
        self.raw_audio_1 = open(self.filename + "-1.raw",'wb')
        self.raw_audio_2 = open(self.filename + "-2.raw",'wb')
        
        for rtp_packet in self.rtp_list_1:
            packet = " ".join(rtp_packet)
            audio = bytearray.fromhex(packet)
            self.raw_audio_1.write(audio)

        for rtp_packet in self.rtp_list_2:
            packet = " ".join(rtp_packet)
            audio = bytearray.fromhex(packet)
            self.raw_audio_2.write(audio)

        self.raw_audio_1.close()
        self.raw_audio_2.close()

        name = rec_time + "_" + self.from_tag + "_" + self.to_tag + ".wav"

        # converting raw audio to wav files and mixing them together
        os.system("sox -t raw -r 8000 -b 8 -c 1 -L -e a-law voip_capture-1.raw recording-1.wav")
        os.system("sox -t raw -r 8000 -b 8 -c 1 -L -e a-law voip_capture-2.raw recording-2.wav")
        os.system("sox -m recording-1.wav recording-2.wav " + name)
        print("Call has been recorded to " + name + ".")
        
        # clean up
        self.rtp_list_1 =[]
        self.rtp_list_2 =[]
        os.system("rm recording-*.wav")

    def scan_passive(self, interface: str):
        print("Capture has started...")
        for packet in pyshark.LiveCapture(interface=interface, display_filter='sip or rtp or icmp'):

            # process SIP packet
            if hasattr(packet, 'sip'):
                try:
                    field_names = packet.sip._all_fields
                    field_values = packet.sip._all_fields.values()

                    sip_packet = zip(field_names, field_values)
                    sip_packet_dict = dict(sip_packet)
                    if ("BYE" in sip_packet_dict["sip.CSeq"]):
                        print("Bye received, ending call...")
                        self.stream_rdy = True

                    # seaching for numbers
                    if (not self.from_rdy or not self.to_rdy):
                        new_from_tag = sip_packet_dict["sip.from.user"]
                        if (re.search("[0-9]{9,}", new_from_tag)):
                        #if ("973" in new_from_tag or "420" in new_from_tag):
                            self.from_tag = new_from_tag
                            self.from_rdy = True
                            #print(self.from_tag)
                        if not self.from_tag:
                            self.from_tag = new_from_tag

                        new_to_tag = sip_packet_dict["sip.to.user"]
                        #if ("973" in new_to_tag or "420" in new_to_tag):
                        if (re.search("[0-9]{9,}", new_to_tag)):
                            self.to_tag = new_to_tag
                            self.to_rdy = True
                            #print(self.to_tag)
                        if not self.to_tag:
                            self.to_tag = new_to_tag

                except OSError:
                    pass
                except asyncio.TimeoutError:
                    pass



            # process RTP packet
            if hasattr(packet, 'rtp'):
                try:
                    rtp = packet[3]
                    if rtp.payload:
                        self.active_call = True
                        self.lastRtpReceived = timer()
                        self.stream_rdy = False
                        if self.first_ssrc:
                            if self.first_ssrc == rtp.ssrc:
                                self.rtp_list_1.append(rtp.payload.split(":"))
                            else:
                                self.rtp_list_2.append(rtp.payload.split(":"))
                        else:
                            self.first_ssrc = rtp.ssrc
                            self.rtp_list_1.append(rtp.payload.split(":"))
                except:
                    pass

            # active call reaches timeout -> end call
            delta = timer() - self.lastRtpReceived
            
            if (self.active_call and delta > 2.0):
                print("RTP stream has ended, processing call... (" + self.from_tag + " >> " + self.to_tag + ")")
                self.stream_rdy = True
                self.active_call = False

            if (self.stream_rdy and self.from_rdy and self.to_rdy):
                self.process_recording()
                return

while True:
    recorder = VoipRecorder("voip_capture").scan_passive("eth0")

