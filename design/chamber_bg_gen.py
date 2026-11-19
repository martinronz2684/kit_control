L='#c9ced6'; D='#3a3d44'; P='#5cc3e3'
B0,W=104,192; R0=B0+W+2          # Baukammer 104–296, Blech, Vorrat 298–490
DL,DR=96,560                      # Deck: links knapp, rechts Parkplatz für den Beschichter
defs='''<pattern id="dots" width="4" height="4" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="0.55" fill="#8b9099"/><circle cx="3" cy="3" r="0.45" fill="#6d727b"/></pattern>'''
s=f'<rect x="{DL}" y="224" width="{DR-DL}" height="196" rx="6" fill="none" stroke="{D}" stroke-width="1.2"/>'
# Deck (Blech): bis an die Kammerkanten, dazwischen offen
s+=f'<path d="M{DL} 224 H{B0-1} M{R0+W+1} 224 H{DR}" stroke="{L}" stroke-width="1.5"/>'
# IR-Heizer: schmal, beide über der Bauplatte
for cx in (150,250):
    s+=f'<path d="M{cx-30} 88 h60 l-5 9 h-50 z" fill="none" stroke="{L}" stroke-width="1.2"/>'
    s+=f'<rect x="{cx-23}" y="99" width="46" height="4.5" rx="2.25" fill="#ff7a45"/>'
s+=f'<path d="M127 106 L{B0+2} 220 M173 106 L196 220 M227 106 L204 220 M273 106 L{B0+W-2} 220" stroke="#ff7a45" stroke-opacity="0.35" stroke-dasharray="3 4"/>'
# Laserkopf mittig über der Bauplatte
s+=f'<rect x="180" y="30" width="40" height="40" rx="6" fill="none" stroke="{L}" stroke-width="1.2"/><path d="M184 22h32 M184 26h32" stroke="{L}"/><rect x="194" y="70" width="12" height="9" fill="none" stroke="{L}" stroke-width="1.2"/><circle cx="212" cy="38" r="1.8" fill="{P}"/>'
open('/tmp/f/chamber_bg.html','w').write(f'<html><body style="margin:0;background:transparent"><svg viewBox="0 0 660 440" width="1320" height="880" xmlns="http://www.w3.org/2000/svg"><defs>{defs}</defs>{s}</svg></body></html>')
