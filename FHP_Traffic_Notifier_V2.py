import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta
import re
from io import BytesIO
from PIL import Image
import os

PUSHOVER_USER_KEY = "YOUR_USER_KEY_HERE"
PUSHOVER_API_TOKEN = "YOUR_API_TOKEN_HERE"
WEB_URL = "https://trafficincidents.flhsmv.gov/SmartWebClient/CadView.aspx"
CHECK_INTERVAL = 5
DEBUG_MODE = True
GENERATE_MAPBOX_MAP = True
ADD_COUNTY_TO_LOCATION = True
# All 67 Florida Counties: Alachua, Baker, Bay, Bradford, Brevard, Broward, Calhoun, Charlotte, Citrus, Clay, Collier, Columbia, DeSoto, Dixie, Duval, Escambia, Flagler, Franklin, Gadsden, Gilchrist, Glades, Gulf, Hamilton, Hardee, Hendry, Hernando, Highlands, Hillsborough, Holmes, Indian River, Jackson, Jefferson, Lafayette, Lake, Lee, Leon, Levy, Liberty, Madison, Manatee, Marion, Martin, Miami-Dade, Monroe, Nassau, Okaloosa, Okeechobee, Orange, Osceola, Palm Beach, Pasco, Pinellas, Polk, Putnam, St. Johns, St. Lucie, Santa Rosa, Sarasota, Seminole, Sumter, Suwannee, Taylor, Union, Volusia, Wakulla, Walton, Washington
FILTER_COUNTIES = ["Alachua", "Baker", "Bay", "Bradford", "Brevard", "Broward", "Calhoun", "Charlotte", "Citrus", "Clay", "Collier", "Columbia", "DeSoto", "Dixie", "Duval", "Escambia", "Flagler", "Franklin", "Gadsden", "Gilchrist", "Glades", "Gulf", "Hamilton", "Hardee", "Hendry", "Hernando", "Highlands", "Hillsborough", "Holmes", "Indian River", "Jackson", "Jefferson", "Lafayette", "Lake", "Lee", "Leon", "Levy", "Liberty", "Madison", "Manatee", "Marion", "Martin", "Miami-Dade", "Monroe", "Nassau", "Okaloosa", "Okeechobee", "Orange", "Osceola", "Palm Beach", "Pasco", "Pinellas", "Polk", "Putnam", "St. Johns", "St. Lucie", "Santa Rosa", "Sarasota", "Seminole", "Sumter", "Suwannee", "Taylor", "Union", "Volusia", "Wakulla", "Walton", "Washington"]
FILTER_INCIDENT_TYPES = []  # Example: ["Vehicle Crash", "Disabled Vehicle"] - Leave empty [] to show all incident types
NEW_INCIDENT_WAIT_TIME = 120
UPDATE_WAIT_TIME = 60
HIGHWAY_NAMES = {'SR-589': 'Suncoast Parkway', 'FLORIDA\'S TPKE': 'Florida\'s Turnpike'}
MAPBOX_TOKEN = "YOUR_MAPBOX_TOKEN_HERE"
PIN_FOLDER = r"C:\Users\YOUR_FOLDER_LOCATION\Map Pins"
PIN_SIZE = 300

sent_incidents, pending_incidents, preloaded, type_change_logged = {}, {}, {}, {}

def get_custom_pin(incident_type, previous_type=None, had_fatality=False):
    t = incident_type.lower()
    if previous_type and "fatality" in t:
        prev = previous_type.lower()
        if "aircraft crash - water" in prev:
            return "Aircraft_water_fatality"
        elif "aircraft crash - land" in prev or "aircraft crash" in prev:
            return "Aircraft_land_fatality"
        elif "crash" in prev:
            return "Crash_fatality"
        elif "fire - structure" in prev:
            return "Structure_fire_fatality"
        elif "fire - vehicle" in prev:
            return "Vehicle_fire_fatality"
        elif "fire - boat" in prev:
            return "Boat_fire_fatality"
        elif "suicide" in prev:
            return "Caution_fatality"
    if had_fatality and "crash" not in t:
        if "aircraft" in t and "water" in t:
            return "Aircraft_water_fatality"
        elif "aircraft" in t:
            return "Aircraft_land_fatality"
        elif "fire - structure" in t or "structure" in t:
            return "Structure_fire_fatality"
        elif "fire - vehicle" in t or "vehicle fire" in t:
            return "Vehicle_fire_fatality"
        elif "fire - boat" in t or "boat" in t:
            return "Boat_fire_fatality"
        elif "suicide" in t or "caution" in t:
            return "Caution_fatality"
    if "disabled patrol" in t: return "Disabled_patrol"
    elif "road closed due to" in t: return "Roadblock"
    elif "traffic light out" in t: return "Traffic_light"
    elif "possible fatality" in t: return "Crash"
    elif "suicide" in t: return "Caution"
    elif "purple" in t: return "Purple_alert"
    elif "silver" in t: return "Silver_alert"
    elif "missing person" in t or "amber alert" in t: return "Alert"
    elif "stolen vehicle" in t: return "Criminal"
    elif "aircraft crash - water" in t: return "Aircraft_water"
    elif "aircraft crash - land" in t or "aircraft crash" in t: return "Aircraft_land"
    elif "fire - boat" in t: return "Boat_fire"
    elif "fire - structure" in t: return "Structure_fire"
    elif "fire - vehicle" in t: return "Vehicle_fire"
    elif "fire - brush/forest" in t or "fire - prescribed burn" in t: return "Brushfire"
    elif "fire" in t: return "Fire"
    elif "construction" in t: return "Construction"
    elif "patrol car crash" in t or "patrol crash" in t: return "Patrol_crash"
    elif "disabled" in t: return "Disabled"
    elif "boat" in t: return "Boat"
    elif "travel advisory" in t: return "Bell"
    elif "crash" in t: return "Crash"
    elif "cone" in t: return "Cone"
    else: return "Caution"

def log_timestamp():
    n = datetime.now()
    tz = {'Eastern Standard Time': 'EST', 'Eastern Daylight Time': 'EDT', 'Central Standard Time': 'CST', 'Central Daylight Time': 'CDT', 'Mountain Standard Time': 'MST', 'Mountain Daylight Time': 'MDT', 'Pacific Standard Time': 'PST', 'Pacific Daylight Time': 'PDT'}.get(time.strftime('%Z', time.localtime()), time.strftime('%Z', time.localtime()))
    return n.strftime(f"[%m/%d/%Y %I:%M:%S %p {tz}]")

def create_map_image(lat, lon, incident_type, previous_type=None, had_fatality=False, retry=0):
    try:
        url = f"https://api.mapbox.com/styles/v1/mapbox/streets-v12/static/{lon},{lat},16,0/1200x675@2x?access_token={MAPBOX_TOKEN}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        base_map = Image.open(BytesIO(r.content)).convert("RGBA")
        pin_file = get_custom_pin(incident_type, previous_type, had_fatality)
        pin_path = os.path.join(PIN_FOLDER, f"{pin_file}.png")
        if os.path.exists(pin_path):
            pin = Image.open(pin_path).convert("RGBA")
            pin.thumbnail((PIN_SIZE, PIN_SIZE), Image.Resampling.LANCZOS)
            scale_factor = min(PIN_SIZE / 634, PIN_SIZE / 975)
            pinpoint_x_in_pin = int(317 * scale_factor)
            pinpoint_y_in_pin = int(920 * scale_factor)
            map_center_x = base_map.width // 2
            map_center_y = base_map.height // 2
            pin_x = map_center_x - pinpoint_x_in_pin
            pin_y = map_center_y - pinpoint_y_in_pin
            base_map.paste(pin, (pin_x, pin_y), pin)
        else:
            print(f"{log_timestamp()} Warning: Pin file not found: {pin_path}")
        buf = BytesIO()
        base_map.save(buf, format='PNG', quality=95)
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"{log_timestamp()} Error creating map (attempt {retry + 1}): {e}")
        if retry < 2:
            time.sleep(2)
            return create_map_image(lat, lon, incident_type, previous_type, had_fatality, retry + 1)
        return None

def proper_title_case(text):
    if not text: return text
    words, result = text.split(), []
    for word in words:
        if "'" in word:
            parts = word.split("'")
            result.append(parts[0].title() + "'" + parts[1].lower() if len(parts) > 1 else parts[0].title())
        else:
            result.append(word.title())
    return ' '.join(result)

def format_incident_type(t):
    if not t: return "Unknown"
    f = re.sub(r'\bw/(?=\S)', 'with ', t, flags=re.IGNORECASE)
    f = re.sub(r'\bw/\s', 'with ', f, flags=re.IGNORECASE)
    f = re.sub(r'\bwith([a-zA-Z])', r'with \1', f, flags=re.IGNORECASE)
    words, result = f.split(), []
    for word in words:
        if len(result) > 0 and word.lower() in ('and', 'with', 'or', 'in', 'on', 'at', 'to', 'for', 'of', 'the'):
            result.append(word.lower())
        elif '/' in word:
            result.append(word.title())
        elif "'" in word:
            result.append(word[0].upper() + word[1:].lower())
        else:
            result.append(word.title())
    return ' '.join(result)

def clean_web_address(web_loc, county=None):
    dir_map = {'[JSOF]': 'Just South of', '[JSO]': 'Just South of', '[JNOF]': 'Just North of', '[JNO]': 'Just North of', '[JEOF]': 'Just East of', '[JEO]': 'Just East of', '[JWOF]': 'Just West of', '[JWO]': 'Just West of', '[SOF]': 'South of', '[NOF]': 'North of', '[WOF]': 'West of', '[EOF]': 'East of', '[XR]': 'Crossroad', '[Ramp To]': 'Ramp to', '[Ramp From]': 'Ramp from', '[RAMP TO]': 'Ramp to', '[RAMP FROM]': 'Ramp from', '[JUST SOUTH OF]': 'Just South of', '[JUST NORTH OF]': 'Just North of', '[JUST EAST OF]': 'Just East of', '[JUST WEST OF]': 'Just West of', '[SOUTH OF]': 'South of', '[NORTH OF]': 'North of', '[EAST OF]': 'East of', '[WEST OF]': 'West of', '[BEFORE]': 'Before', '[BEYOND]': 'Beyond'}
    has_front = 'in front of' in web_loc.lower()
    has_dir = any(abbrev in web_loc for abbrev in dir_map.keys())
    web_loc = re.sub(r'\[(NB|SB|EB|WB)\s+(JSOF|JSO|JNOF|JNO|JEOF|JEO|JWOF|JWO|SOF|NOF|WOF|EOF|XR|Ramp To|Ramp From|JUST SOUTH OF|JUST NORTH OF|JUST EAST OF|JUST WEST OF|SOUTH OF|NORTH OF|EAST OF|WEST OF|BEFORE|BEYOND)\]', lambda m: f"{m.group(1).upper()} {dir_map.get(f'[{m.group(2).upper()}]', dir_map.get(f'[{m.group(2)}]', m.group(2).upper()))}", web_loc, flags=re.IGNORECASE)
    for abbrev, trans in dir_map.items():
        web_loc = web_loc.replace(abbrev, trans)
    is_hwy_mm = "x[MM" in web_loc and "[MM" in web_loc
    is_inter = "x[" in web_loc and not is_hwy_mm
    is_reg = "[" in web_loc and "]" in web_loc and not is_hwy_mm and not is_inter
    if is_hwy_mm:
        orig = web_loc
        hwy = web_loc[:web_loc.find("[")].strip()
        is_exit = "[EXIT]" in web_loc.upper()
        mm_s, mm_e = web_loc.find("[MM") + 3, web_loc.find("]", web_loc.find("[MM") + 3)
        loc = f"{hwy} Exit @ MM{web_loc[mm_s:mm_e]}" if is_exit and mm_s != -1 and mm_e != -1 else (f"{hwy} @ MM{web_loc[mm_s:mm_e]}" if mm_s != -1 and mm_e != -1 else web_loc)
        fb_s, fb_e = orig.rfind("["), orig.rfind("]")
        city = orig[fb_s + 1:fb_e].strip() if fb_s != -1 and fb_e != -1 and not orig[fb_s + 1:fb_e].strip().startswith("MM") else None
    elif is_inter:
        if "EXIT [" in web_loc.upper():
            orig = web_loc
            exit_pos = web_loc.upper().find("EXIT [")
            hwy = web_loc[:exit_pos].strip()
            fb_s, fb_e = web_loc.find("[", exit_pos) + 1, web_loc.find("]", web_loc.find("[", exit_pos) + 1)
            loc = f"{hwy} Exit & {web_loc[fb_s:fb_e].strip()}"
            fn_s, fn_e = orig.rfind("["), orig.rfind("]")
            city = orig[fn_s + 1:fn_e].strip() if fn_s != -1 and fn_e != -1 else None
        else:
            orig = web_loc
            has_d = any(p in web_loc for p in ['Just South of', 'Just North of', 'Just East of', 'Just West of', 'South of', 'North of', 'East of', 'West of', 'Crossroad', 'Ramp to', 'Ramp from', 'Before', 'Beyond'])
            if has_d:
                parts = web_loc.split("x[")
                if len(parts) == 2:
                    base = parts[0].strip()
                    d_found, sp = None, -1
                    for phrase in ['Just South of', 'Just North of', 'Just East of', 'Just West of', 'South of', 'North of', 'East of', 'West of', 'Crossroad', 'Ramp to', 'Ramp from', 'Before', 'Beyond']:
                        if phrase in base:
                            sp, d_found = base.find(phrase), phrase
                            break
                    street = parts[1].split("]")[0].strip()
                    loc = f"{base[:sp].strip()} {d_found} {street}" if sp != -1 else f"{base} {street}"
                else:
                    loc = web_loc
            else:
                parts = web_loc.split("x[")
                loc = f"{parts[0].strip()} & {parts[1].split(']')[0].strip()}"
            fn_s, fn_e = orig.rfind("["), orig.rfind("]")
            pot_city = orig[fn_s + 1:fn_e].strip() if fn_s != -1 and fn_e != -1 else None
            city = None
            if pot_city and pot_city not in loc and not pot_city.isdigit():
                city = pot_city
    elif is_reg:
        bs, be = web_loc.find("["), web_loc.find("]")
        if bs != -1 and be != -1:
            bc = web_loc[bs + 1:be].strip()
            loc = web_loc[:bs].strip()
            if bc.isdigit():
                loc = f"{bc} {loc}"
                city = None
            elif bc.upper().startswith("RP "):
                ramp = bc[3:].strip()
                if "/" in ramp:
                    parts = ramp.split("/")
                    sec = parts[1].strip() if len(parts) > 1 else ""
                    if " ENT " in sec.upper() or sec.upper().startswith("ENT "):
                        ep = sec.upper().find(" ENT ") if " ENT " in sec.upper() else (0 if sec.upper().startswith("ENT ") else -1)
                        if ep != -1:
                            bef = sec[:ep].strip() if ep > 0 else ""
                            aft = sec[ep:].strip() if ep > 0 else sec
                            en = aft[4:].strip() if aft.upper().startswith("ENT ") else aft.split()[-1]
                            sec = f"{bef} @ Entrance {en}" if bef else f"@ Entrance {en}"
                    elif " EXT " in sec.upper() or sec.upper().startswith("EXT "):
                        ex = sec.upper().find(" EXT ") if " EXT " in sec.upper() else (0 if sec.upper().startswith("EXT ") else -1)
                        if ex != -1:
                            bef = sec[:ex].strip() if ex > 0 else ""
                            aft = sec[ex:].strip() if ex > 0 else sec
                            exn = aft[4:].strip() if aft.upper().startswith("EXT ") else aft.split()[-1]
                            sec = f"{bef} Exit {exn}" if bef else f"Exit {exn}"
                    loc = f"{loc} Ramp & {sec}"
                else:
                    loc = f"{loc} Ramp {ramp}"
                city = None
            else:
                city = bc
        else:
            loc, city = web_loc, None
    else:
        loc, city = web_loc, None

    def proc_paren(m):
        ins = m.group(1)
        words = ins.split()
        proc = []
        for w in words:
            up = w.upper()
            if up in ("NB", "SB", "EB", "WB", "SW", "NW", "SE", "NE"):
                proc.append(up)
            elif up.startswith(("SR-", "US-", "I-", "CR-")):
                proc.append(up)
            else:
                proc.append(w)
        return '(' + ' '.join(proc) + ')'

    loc = re.sub(r'\(([^)]+)\)', proc_paren, loc)
    dir_phrases = ['Just South of', 'Just North of', 'Just East of', 'Just West of', 'South of', 'North of', 'East of', 'West of', 'Crossroad', 'Ramp to', 'Ramp from', 'Before', 'Beyond']
    has_d_loc = any(phrase in loc for phrase in dir_phrases)
    words = loc.split()
    i = 0
    while i < len(words):
        word = words[i]
        strip = word.strip('(),')
        pre = word[:len(word) - len(word.lstrip('('))]
        suf = word[len(word.rstrip('),')):]
        up = strip.upper()
        if i < len(words) - 1:
            two = f"{strip} {words[i + 1].strip(',).')}" .upper()
            if two in HIGHWAY_NAMES:
                words[i] = pre + HIGHWAY_NAMES[two] + suf
                words[i + 1] = ""
                i += 2
                continue
        if up.startswith("MM") and up[2:].isdigit() and is_hwy_mm:
            hd = False
            if i >= 2 and ' '.join([words[i - 2].strip('(),'), words[i - 1].strip('(),')]).lower() in ['just south', 'just north', 'just east', 'just west']:
                hd = True
            elif i >= 1 and words[i - 1].strip('(),').lower() in ['south', 'north', 'east', 'west']:
                hd = True
            if i > 0 and words[i - 1].strip('(),').upper() in ("NB", "SB", "EB", "WB", "I-4", "I-75", "SR-54", "US-41", "SR-589") and not hd:
                ps = words[i - 1].strip('(),')
                pp = words[i - 1][:len(words[i - 1]) - len(words[i - 1].lstrip('('))]
                psu = words[i - 1][len(words[i - 1].rstrip(')',)):]
                words[i - 1] = pp + ps + f" @ {strip}" + psu
                words[i] = ""
            elif i >= 2 and ' '.join([words[i - 2].strip('(),'), words[i - 1].strip('(),')]).lower() in ['just south', 'just north', 'just east', 'just west']:
                words[i - 2], words[i - 1], words[i] = f"{words[i - 2]} {words[i - 1]} {strip}", "", ""
            elif i >= 1 and words[i - 1].strip('(),').lower() in ['south', 'north', 'east', 'west']:
                words[i - 1], words[i] = f"{words[i - 1]} {strip}", ""
        elif up in ("NB", "SB", "EB", "WB", "SW", "NW", "SE", "NE"):
            words[i] = pre + up + suf
        elif up.startswith(("CR-", "SR-", "US-", "I-")):
            if up == "SR-589" and county and county.upper() == "HILLSBOROUGH":
                words[i] = pre + up + suf
            else:
                words[i] = pre + HIGHWAY_NAMES.get(up, up) + suf
        elif up.startswith("MM") and len(up) > 2 and up[2:].isdigit():
            words[i] = pre + up + suf
        elif up in ("EXIT", "ENTRANCE", "RAMP"):
            words[i] = pre + up.title() + suf
        elif re.match(r'^\d+(ST|ND|RD|TH)$', up):
            m = re.match(r'^(\d+)(ST|ND|RD|TH)$', up)
            words[i] = pre + f"{m.group(1)}{m.group(2).lower()}" + suf
        elif up.startswith(("SR-", "US-", "I-", "CR-")) or up in ("NB", "SB", "EB", "WB", "SW", "NW", "SE", "NE"):
            words[i] = pre + up + suf
        elif strip.lower() not in ['just', 'south', 'north', 'east', 'west', 'of', 'crossroad', 'ramp', 'to', 'from', 'before', 'beyond']:
            words[i] = pre + (proper_title_case(strip) if "'" in strip else strip.title()) + suf
        i += 1
    loc = re.sub(r'\s+', ' ', re.sub(r'(NB|SB|EB|WB)\s*X\s*', r'\1 ', re.sub(r'X\s*@', '@', re.sub(r'\s+X\s+|^X\s+|\s+X$', ' ', " ".join(w for w in words if w))))).strip()
    loc = re.sub(r'(Just South of|Just North of|Just East of|Just West of|South of|North of|East of|West of|Ramp to|Ramp from|Before|Beyond)\s+@\s*MM(\d+)', r'\1 MM\2', loc)
    if has_dir or has_d_loc:
        for phrase in ['Just South of', 'Just North of', 'Just East of', 'Just West of', 'South of', 'North of', 'East of', 'West of', 'Crossroad', 'Ramp to', 'Ramp from', 'Before', 'Beyond']:
            pattern = f' {phrase} '
            if pattern in loc and f', {phrase}' not in loc:
                loc = loc.replace(pattern, f', {phrase} ')
                break
    loc = re.sub(r',\s*Just,\s+(South|North|East|West)\s+of', r', Just \1 of', loc)
    if has_front and not loc.startswith('In Front of'):
        loc = f"In Front of {loc}"
    return f"{loc}, {proper_title_case(city)}" if city and city.lower() not in loc.lower() else loc

def send_pushover_notification(title, message, img_data=None):
    data = {"token": PUSHOVER_API_TOKEN, "user": PUSHOVER_USER_KEY, "title": title, "message": message}
    files = {}
    if img_data:
        img_data.seek(0)
        files = {"attachment": ("map.png", img_data, "image/png")}
    response = requests.post("https://api.pushover.net/1/messages.json", data=data, files=files if files else None)
    if DEBUG_MODE:
        print(f"{log_timestamp()} Pushover notification {'sent' if response.status_code == 200 else 'failed to send'}: {title}\n")
    if response.status_code != 200:
        print(f"Failed to send Pushover notification: {response.text}\n")

def fetch_incidents():
    try:
        response = requests.get(WEB_URL, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        update_panel = soup.find('span', {'id': 'UpdatePanel2'})
        if not update_panel:
            return []
        rows = update_panel.find_all('tr', class_='dxgvDataRow')
        incidents = []
        for row in rows:
            cells = row.find_all('td', class_='dxgv')
            if len(cells) < 9:
                continue
            county_cell = cells[4]
            link = county_cell.find('a')
            cad = None
            if link and 'onclick' in link.attrs:
                cad_match = re.search(r"popUP_MapInfo\('([^']+)'\)", link['onclick'])
                if cad_match:
                    cad = cad_match.group(1)
            if not cad:
                continue
            county = county_cell.get_text(strip=True)
            if FILTER_COUNTIES and county.upper() not in [c.upper() for c in FILTER_COUNTIES]:
                continue
            incidents.append({'cad': cad, 'type': cells[0].get_text(strip=True), 'reported': cells[1].get_text(strip=True), 'lat': cells[7].get_text(strip=True), 'lon': cells[8].get_text(strip=True), 'county': county, 'location': cells[5].get_text(strip=True), 'remarks': cells[6].get_text(strip=True)})
        return incidents
    except Exception as e:
        print(f"Error fetching incidents: {e}")
        return []

def format_time(reported_time):
    try:
        dt = datetime.strptime(reported_time, "%m/%d/%Y %H:%M:%S")
        incident_hour = dt.hour
        current_hour = datetime.now().hour
        if incident_hour == 0:
            display_hour = 12
        elif incident_hour <= 12:
            display_hour = incident_hour
        else:
            display_hour = incident_hour - 12
        am_pm = "AM" if current_hour < 12 else "PM"
        return f"{display_hour}:{dt.strftime('%M')} {am_pm}"
    except:
        return reported_time or "Unknown time"

def extract_incident_data(incident):
    remarks = incident['remarks'].title() if incident['remarks'] else ""
    if remarks:
        remarks = remarks.replace('&nbsp;', '').strip()
        if ("GMT" in remarks or any(m in remarks for m in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])) and re.search(r'\b(GMT|UTC)\b|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b', remarks):
            remarks = ""
    loc = clean_web_address(incident['location'], incident['county']) if incident['location'] else "No location provided"
    
    if ADD_COUNTY_TO_LOCATION and incident.get('county'):
        county_name = proper_title_case(incident['county'])
        if county_name.lower() not in loc.lower():
            loc = f"{loc}, {county_name} County"
    
    return {"cad": incident['cad'], "type": format_incident_type(incident['type']), "location": loc, "remarks": remarks, "reported": format_time(incident['reported']), "lat": incident['lat'], "lon": incident['lon'], "map_link": f"https://maps.google.com/?q={incident['lat']},{incident['lon']}" if incident['lat'] and incident['lon'] else ""}

def send_incident_notification(incident_data, is_update=False, previous_types=None, previous_locations=None, previous_remarks=None, stored_time=None):
    title = f"UPDATE: {incident_data['type']}" if is_update else incident_data['type']
    msg = f"{'Previous Incident Type' if len(previous_types) == 1 else 'Previous Incident Types'}: {', '.join(previous_types)}\n" if is_update and previous_types else ""
    msg += f"Location: {incident_data['location']}\n"
    msg += f"{'Previous Location' if len(previous_locations) == 1 else 'Previous Locations'}: {', '.join(previous_locations)}\n" if is_update and previous_locations and len(previous_locations) > 0 else ""
    msg += f"Remark: {incident_data['remarks'] if incident_data['remarks'] else 'No Remarks Provided'}\n"
    msg += f"{'Previous Remark' if len(previous_remarks) == 1 else 'Previous Remarks'}: {', '.join(previous_remarks)}\n" if is_update and previous_remarks and len(previous_remarks) > 0 else ""
    reported_time = stored_time if is_update and stored_time else incident_data['reported']
    msg += f"Reported: {reported_time}\nMap: {incident_data['map_link']}"
    
    map_img = None
    if GENERATE_MAPBOX_MAP and incident_data.get('lat') and incident_data.get('lon'):
        try:
            previous_type = previous_types[0] if (is_update and previous_types and len(previous_types) > 0) else None
            had_fatality = False
            if "fatality" in incident_data['type'].lower() and "possible" not in incident_data['type'].lower():
                had_fatality = True
                if incident_data['type'].lower().strip() == "fatality" and not previous_type:
                    previous_type = "Crash"
            if is_update and previous_types:
                prev_had_fatality = any("fatality" in pt.lower() and "possible" not in pt.lower() for pt in previous_types)
                if prev_had_fatality:
                    original_type = None
                    for pt in reversed(previous_types):
                        pt_lower = pt.lower().strip()
                        if "fatality" not in pt_lower:
                            original_type = pt
                            break
                    
                    if original_type:
                        current_normalized = ' '.join(incident_data['type'].lower().split())
                        original_normalized = ' '.join(original_type.lower().split())
                        
                        if (current_normalized == original_normalized and
                            "crash" not in original_normalized and
                            "crash" not in current_normalized):
                            had_fatality = True
                            previous_type = original_type
            map_img = create_map_image(float(incident_data['lat']), float(incident_data['lon']), incident_data['type'], previous_type, had_fatality)
            if DEBUG_MODE:
                print(f"{log_timestamp()} DEBUG: {'New CAD incident' if not is_update else 'CAD incident'}: {incident_data['cad']} - Map generated {'successfully' if map_img else 'unsuccessfully'}\n")
        except Exception as e:
            if DEBUG_MODE:
                print(f"{log_timestamp()} DEBUG: {'New CAD incident' if not is_update else 'CAD incident'}: {incident_data['cad']} - Map generation unsuccessful: {e}\n")
    elif not GENERATE_MAPBOX_MAP and DEBUG_MODE:
        print(f"{log_timestamp()} DEBUG: {'New CAD incident' if not is_update else 'CAD incident'}: {incident_data['cad']} - Map generation disabled\n")
    
    send_pushover_notification(title, msg, map_img)
    
    if DEBUG_MODE:
        remarks_text = incident_data['remarks'] if incident_data['remarks'] else "No Remarks Provided"
        print(f"{log_timestamp()} Information sent:")
        print(f"{'New CAD Incident' if not is_update else 'CAD Incident'}: {incident_data['cad']}")
        print(f"Incident Type: {incident_data['type']}")
        if is_update and previous_types:
            print(f"{'Previous Incident Type' if len(previous_types) == 1 else 'Previous Incident Types'}: {', '.join(previous_types)}")
        print(f"Location: {incident_data['location']}")
        if is_update and previous_locations and len(previous_locations) > 0:
            print(f"{'Previous Location' if len(previous_locations) == 1 else 'Previous Locations'}: {', '.join(previous_locations)}")
        print(f"Remark: {remarks_text}")
        if is_update and previous_remarks and len(previous_remarks) > 0:
            print(f"{'Previous Remark' if len(previous_remarks) == 1 else 'Previous Remarks'}: {', '.join(previous_remarks)}")
        print(f"Reported: {reported_time}")
        print(f"Map: {incident_data['map_link']}")
        print("-" * 133)

def process_pending_notifications():
    current_time = datetime.now()
    to_notify = []
    for cad, pending in list(pending_incidents.items()):
        incident_data, is_update, last_remarks = pending["data"], pending["is_update"], pending["last_remarks"]
        if incident_data['remarks'] and incident_data['remarks'] != last_remarks:
            if DEBUG_MODE:
                print(f"{log_timestamp()} DEBUG: {'New CAD incident' if not is_update else 'CAD incident'}: {cad} - {'Updated remark added' if is_update else 'Remark added'}: '{incident_data['remarks']}'\n")
            to_notify.append(cad)
        elif current_time >= pending["wait_until"]:
            if DEBUG_MODE:
                remarks_status = "new remarks provided" if is_update and incident_data['remarks'] != last_remarks else ("remarks provided" if incident_data['remarks'] else "no remarks provided")
                print(f"\n{log_timestamp()} DEBUG: {'New CAD incident' if not is_update else 'CAD incident'}: {cad} - Wait time expired for {'update' if is_update else 'incident'}, {remarks_status}\n")
                if incident_data['remarks']:
                    remark_text = "Updated remark added" if is_update and incident_data['remarks'] != last_remarks else ("Remark remained" if is_update else "Remark added")
                    print(f"{log_timestamp()} DEBUG: {'New CAD incident' if not is_update else 'CAD incident'}: {cad} - {remark_text}: '{incident_data['remarks']}'\n")
            to_notify.append(cad)
    
    for cad in to_notify:
        pending = pending_incidents[cad]
        incident_data, is_update = pending["data"], pending["is_update"]
        if is_update:
            record = sent_incidents.get(cad)
            if not record:
                continue
            previous_types_list = record.get("previous_types")
            previous_types = [record["type"]] + (previous_types_list if previous_types_list is not None else [])
            previous_locations = None
            if incident_data['location'] != record.get("location", ""):
                previous_locations_list = record.get("previous_locations")
                previous_locations = previous_locations_list if previous_locations_list is not None else []
                if record.get("location"):
                    previous_locations = [record["location"]] + previous_locations
            current_stored_remark = record.get("remark", "")
            previous_remarks = None
            if incident_data['remarks'] != current_stored_remark:
                previous_remarks_list = record.get("previous_remarks")
                previous_remarks = previous_remarks_list if previous_remarks_list is not None else []
                if current_stored_remark:
                    previous_remarks = [current_stored_remark] + previous_remarks
                if DEBUG_MODE and previous_remarks:
                    print(f"{log_timestamp()} DEBUG: CAD incident: {cad} - {'Previous remark' if len(previous_remarks) == 1 else 'Previous remarks'}: {f'"{previous_remarks[0]}"' if len(previous_remarks) == 1 else f'"{chr(34)+chr(44)+chr(32)+chr(34).join(previous_remarks)}"'}\n")
            send_incident_notification(incident_data, is_update=True, previous_types=previous_types, previous_locations=previous_locations, previous_remarks=previous_remarks, stored_time=record.get("reported"))
            sent_incidents[cad]["previous_types"], sent_incidents[cad]["type"] = previous_types, incident_data['type']
            if incident_data['location'] != record.get("location", ""):
                if "previous_locations" not in sent_incidents[cad]:
                    sent_incidents[cad]["previous_locations"] = []
                if record.get("location"):
                    sent_incidents[cad]["previous_locations"].insert(0, record["location"])
                sent_incidents[cad]["location"] = incident_data['location']
            if incident_data['remarks'] != record.get("remark", ""):
                if "previous_remarks" not in sent_incidents[cad]:
                    sent_incidents[cad]["previous_remarks"] = []
                if record.get("remark"):
                    sent_incidents[cad]["previous_remarks"].insert(0, record["remark"])
                sent_incidents[cad]["remark"] = incident_data['remarks']
        else:
            send_incident_notification(incident_data, is_update=False)
            sent_incidents[cad] = {"type": incident_data['type'], "previous_types": [], "location": incident_data['location'], "previous_locations": [], "remark": incident_data['remarks'], "previous_remarks": [], "reported": incident_data['reported']}
        del pending_incidents[cad]

def process_incident(incident_raw):
    incident_data = extract_incident_data(incident_raw)
    if not incident_data:
        return
    cad, incident_type = incident_data["cad"], incident_data["type"]
    is_filtered = FILTER_INCIDENT_TYPES and any(filtered_type.lower() == incident_type.lower() for filtered_type in FILTER_INCIDENT_TYPES)
    
    if is_filtered and cad in sent_incidents:
        if incident_data['location'] != sent_incidents[cad].get("location", ""):
            sent_incidents[cad]["location"] = incident_data['location']
        if incident_data['remarks'] != sent_incidents[cad].get("remark", ""):
            sent_incidents[cad]["remark"] = incident_data['remarks']
        return
    
    if is_filtered and cad not in sent_incidents:
        if DEBUG_MODE:
            print(f"{log_timestamp()} DEBUG: Filtered incident type: {incident_type}")
            print("-" * 133)
        sent_incidents[cad] = {"type": incident_type, "previous_types": [], "location": incident_data['location'], "previous_locations": [], "remark": incident_data['remarks'], "previous_remarks": [], "reported": incident_data['reported']}
        return
    
    if cad in sent_incidents:
        record = sent_incidents[cad]
        if incident_type != record["type"]:
            type_change_key = f"{cad}_{record['type']}_to_{incident_type}"
            if type_change_key not in type_change_logged:
                if DEBUG_MODE:
                    print(f"{log_timestamp()} DEBUG: CAD incident: {cad} - Incident type changed from '{record['type']}' to '{incident_type}'\n")
                    if incident_data['location'] != record.get("location", ""):
                        print(f"{log_timestamp()} DEBUG: CAD incident: {cad} - Raw location: {' '.join(incident_raw['location'].split())}\n")
                        print(f"{log_timestamp()} DEBUG: CAD incident: {cad} - Formatted location: {incident_data['location']}\n")
                        print(f"{log_timestamp()} DEBUG: CAD incident: {cad} - New location: {incident_data['location']}\n")
                    else:
                        print(f"{log_timestamp()} DEBUG: CAD incident: {cad} - No updates on location\n")
                type_change_logged[type_change_key] = True
            if cad in pending_incidents:
                pending_incidents[cad]["data"] = incident_data
            else:
                pending_incidents[cad] = {"data": incident_data, "wait_until": datetime.now() + timedelta(seconds=UPDATE_WAIT_TIME), "is_update": True, "last_remarks": sent_incidents[cad].get("remark", "")}
                if DEBUG_MODE:
                    print(f"{log_timestamp()} DEBUG: CAD incident: {cad} - Added to pending updates, waiting {UPDATE_WAIT_TIME} seconds for updated remark\n")
                    print("")
        elif cad in sent_incidents:
            if incident_data['location'] != sent_incidents[cad].get("location", ""):
                sent_incidents[cad]["location"] = incident_data['location']
            if incident_data['remarks'] != sent_incidents[cad].get("remark", ""):
                sent_incidents[cad]["remark"] = incident_data['remarks']
    else:
        if not preloaded.get(cad, False):
            if cad in pending_incidents:
                pending_incidents[cad]["data"] = incident_data
            else:
                pending_incidents[cad] = {"data": incident_data, "wait_until": datetime.now() + timedelta(seconds=NEW_INCIDENT_WAIT_TIME), "is_update": False, "last_remarks": ""}
                if DEBUG_MODE:
                    print(f"{log_timestamp()} DEBUG: New CAD incident: {cad} - New incident added to pending, waiting {NEW_INCIDENT_WAIT_TIME} seconds for remark\n")
                    print(f"{log_timestamp()} DEBUG: New CAD incident: {cad} - Raw location: {' '.join(incident_raw['location'].split())}\n")
                    print(f"{log_timestamp()} DEBUG: New CAD incident: {cad} - Formatted location: {incident_data['location']}\n")
        else:
            sent_incidents[cad] = {"type": incident_type, "previous_types": [], "location": incident_data['location'], "previous_locations": [], "remark": incident_data['remarks'], "previous_remarks": [], "reported": incident_data['reported']}

def main():
    print("Starting FHP Traffic Incident Notifier V2 - Developed by Ryan Watern\n")
    print(f"Counties: {', '.join(FILTER_COUNTIES)}\nFiltered Incident Types: {', '.join(FILTER_INCIDENT_TYPES) if FILTER_INCIDENT_TYPES else 'None'}\nCheck interval: {CHECK_INTERVAL} seconds\nNew incident remark wait time: {NEW_INCIDENT_WAIT_TIME} seconds\nUpdate remark wait time: {UPDATE_WAIT_TIME} seconds\nGenerate Mapbox Map: {'ON' if GENERATE_MAPBOX_MAP else 'OFF'}\nAdd County to Location: {'ON' if ADD_COUNTY_TO_LOCATION else 'OFF'}\nDebug mode: {'ON' if DEBUG_MODE else 'OFF'}\n" + "-" * 133 + "\nPreloading existing incidents...")
    print("")
    filtered_count = 0
    for incident in fetch_incidents():
        incident_data = extract_incident_data(incident)
        if incident_data:
            cad = incident_data["cad"]
            preloaded[cad] = True
            sent_incidents[cad] = {"type": incident_data["type"], "previous_types": [], "location": incident_data['location'], "previous_locations": [], "remark": incident_data['remarks'], "previous_remarks": [], "reported": incident_data['reported']}
            if FILTER_INCIDENT_TYPES and any(filtered_type.lower() == incident_data["type"].lower() for filtered_type in FILTER_INCIDENT_TYPES):
                filtered_count += 1
    if DEBUG_MODE:
        print(f"{log_timestamp()} DEBUG: Preloaded {len(preloaded)} existing incidents ({filtered_count} filtered)\n")
    print("Monitoring for new incidents and updates...\n" + "-" * 133)
    while True:
        try:
            for incident in fetch_incidents():
                process_incident(incident)
            process_pending_notifications()
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print("\nShutting down monitor...")
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
