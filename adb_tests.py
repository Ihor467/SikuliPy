from sikulipy.android import ADBClient 
                                                                                                                                                                                                   
dev = ADBClient().device()          # first attached device                                                                                                                                                                               
dev.tap(500, 1000)                                                                                                                                                                                                                        
dev.swipe(300, 1500, 300, 500, duration_ms=300)                                                                                                                                                                                           
png_bytes = dev.screencap_png()
with open("android_screen.png", "wb") as f:
    f.write(png_bytes)
print(f"wrote android_screen.png ({len(png_bytes)} bytes)")



