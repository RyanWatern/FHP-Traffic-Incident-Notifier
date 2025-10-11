import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta
import re

PUSHOVER_USER_KEY = "YOUR_USER_KEY_HERE"
PUSHOVER_API_TOKEN = "YOUR_API_TOKEN_HERE"
WEB_URL = "https://trafficincidents.flhsmv.gov/SmartWebClient/CadView.aspx"
CHECK_INTERVAL = 5
DEBUG_MODE = True
# All 67 Florida Counties: Alachua, Baker, Bay, Bradford, Brevard, Broward, Calhoun, Charlotte, Citrus, Clay, Collier, Columbia, DeSoto, Dixie, Duval, Escambia, Flagler, Franklin, Gadsden, Gilchrist, Glades, Gulf, Hamilton, Hardee, Hendry, Hernando, Highlands, Hillsborough, Holmes, Indian River, Jackson, Jefferson, Lafayette, Lake, Lee, Leon, Levy, Liberty, Madison, Manatee, Marion, Martin, Miami-Dade, Monroe, Nassau, Okaloosa, Okeechobee, Orange, Osceola, Palm Beach, Pasco, Pinellas, Polk, Putnam, St. Johns, St. Lucie, Santa Rosa, Sarasota, Seminole, Sumter, Suwannee, Taylor, Union, Volusia, Wakulla, Walton, Washington
FILTER_COUNTIES = ["Alachua", "Baker", "Bay", "Bradford", "Brevard", "Broward", "Calhoun", "Charlotte", "Citrus", "Clay", "Collier", "Columbia", "DeSoto", "Dixie", "Duval", "Escambia", "Flagler", "Franklin", "Gadsden", "Gilchrist", "Glades", "Gulf", "Hamilton", "Hardee", "Hendry", "Hernando", "Highlands", "Hillsborough", "Holmes", "Indian River", "Jackson", "Jefferson", "Lafayette", "Lake", "Lee", "Leon", "Levy", "Liberty", "Madison", "Manatee", "Marion", "Martin", "Miami-Dade", "Monroe", "Nassau", "Okaloosa", "Okeechobee", "Orange", "Osceola", "Palm Beach", "Pasco", "Pinellas", "Polk", "Putnam", "St. Johns", "St. Lucie", "Santa Rosa", "Sarasota", "Seminole", "Sumter", "Suwannee", "Taylor", "Union", "Volusia", "Wakulla", "Walton", "Washington"]
FILTER_INCIDENT_TYPES = []  # Example: ["Vehicle Crash", "Disabled Vehicle"] - Leave empty [] to show all incident types
NEW_INCIDENT_WAIT_TIME = 120
UPDATE_WAIT_TIME = 60
HIGHWAY_NAMES = {'SR-589': 'Suncoast Parkway'}
sent_incidents, pending_incidents, preloaded, type_change_logged = {}, {}, {}, {}

def log_timestamp():
    now = datetime.now()
    tz_name = time.strftime('%Z', time.localtime())
    # Abbreviate common timezone names
    tz_abbreviations = {
        'Eastern Standard Time': 'EST',
        'Eastern Daylight Time': 'EDT',
        'Central Standard Time': 'CST',
        'Central Daylight Time': 'CDT',
        'Mountain Standard Time': 'MST',
        'Mountain Daylight Time': 'MDT',
        'Pacific Standard Time': 'PST',
        'Pacific Daylight Time': 'PDT'
    }
    tz_name = tz_abbreviations.get(tz_name, tz_name)
    return now.strftime(f"[%m/%d/%Y %I:%M:%S %p {tz_name}]")

def format_incident_type(incident_type):
    if not incident_type:
        return "Unknown"
    formatted = re.sub(r'\bw/(?=\S)', 'with ', incident_type, flags=re.IGNORECASE)
    formatted = re.sub(r'\bw/\s', 'with ', formatted, flags=re.IGNORECASE)
    formatted = re.sub(r'\bw/$', 'with', formatted, flags=re.IGNORECASE)
    formatted = re.sub(r'\bwith([a-zA-Z])', r'with \1', formatted, flags=re.IGNORECASE)
    words, result = formatted.split(), []
    for word in words:
        if len(result) > 0 and word.lower() in ('and','with','or','in','on','at','to','for','of','the'):
            result.append(word.lower())
        elif '/' in word:
            result.append(word.title())
        else:
            result.append(word.title())
    return ' '.join(result)

def clean_web_address(web_location):
    directional_map = {'[JSOF]':'Just South of','[JSO]':'Just South of','[JNOF]':'Just North of','[JNO]':'Just North of','[JEOF]':'Just East of','[JEO]':'Just East of','[JWOF]':'Just West of','[JWO]':'Just West of','[SOF]':'South of','[NOF]':'North of','[WOF]':'West of','[EOF]':'East of','[XR]':'Crossroad'}
    web_location = re.sub(r'\[(NB|SB|EB|WB)\s+(JSOF|JSO|JNOF|JNO|JEOF|JEO|JWOF|JWO|SOF|NOF|WOF|EOF|XR)\]',lambda m:f"{m.group(1).upper()} {directional_map.get(f'[{m.group(2).upper()}]',m.group(2).upper())}",web_location,flags=re.IGNORECASE)
    for abbrev, translation in directional_map.items():
        web_location = web_location.replace(abbrev, translation)
    is_highway_mm = "x[MM" in web_location and "[MM" in web_location
    is_intersection = "x[" in web_location and not is_highway_mm
    is_regular_address = "[" in web_location and "]" in web_location and not is_highway_mm and not is_intersection
    if is_highway_mm:
        original_location = web_location
        highway_part = web_location[:web_location.find("[")].strip()
        is_exit_format = "[EXIT]" in web_location.upper()
        mm_start, mm_end = web_location.find("[MM")+3, web_location.find("]",web_location.find("[MM")+3)
        location = f"{highway_part} Exit @ MM{web_location[mm_start:mm_end]}" if is_exit_format and mm_start!=-1 and mm_end!=-1 else (f"{highway_part} @ MM{web_location[mm_start:mm_end]}" if mm_start!=-1 and mm_end!=-1 else web_location)
        final_bracket_start, final_bracket_end = original_location.rfind("["), original_location.rfind("]")
        city = original_location[final_bracket_start+1:final_bracket_end].strip() if final_bracket_start!=-1 and final_bracket_end!=-1 and not original_location[final_bracket_start+1:final_bracket_end].strip().startswith("MM") else None
    elif is_intersection:
        if "EXIT [" in web_location.upper():
            original_location = web_location
            exit_pos = web_location.upper().find("EXIT [")
            highway_part = web_location[:exit_pos].strip()
            first_bracket_start, first_bracket_end = web_location.find("[",exit_pos)+1, web_location.find("]",web_location.find("[",exit_pos)+1)
            location = f"{highway_part} Exit & {web_location[first_bracket_start:first_bracket_end].strip()}"
            final_bracket_start, final_bracket_end = original_location.rfind("["), original_location.rfind("]")
            city = original_location[final_bracket_start+1:final_bracket_end].strip() if final_bracket_start!=-1 and final_bracket_end!=-1 else None
        else:
            original_location = web_location
            has_directional = any(p in web_location for p in['Just South of','Just North of','Just East of','Just West of','South of','North of','East of','West of','Crossroad'])
            if has_directional:
                parts = web_location.split("x[")
                if len(parts)==2:
                    base_part = parts[0].strip()
                    directional_found, split_position = None, -1
                    for phrase in['Just South of','Just North of','Just East of','Just West of','South of','North of','East of','West of','Crossroad']:
                        if phrase in base_part:
                            split_position, directional_found = base_part.find(phrase), phrase
                            break
                    street_part = parts[1].split("]")[0].strip()
                    if split_position!=-1:
                        highway_part = base_part[:split_position].strip()
                        location = f"{highway_part}, {directional_found} {street_part}"
                    else:
                        location = f"{base_part}, {street_part}"
                else:
                    location = web_location
            else:
                parts = web_location.split("x[")
                location = f"{parts[0].strip()} & {parts[1].split(']')[0].strip()}"
            final_bracket_start, final_bracket_end = original_location.rfind("["), original_location.rfind("]")
            potential_city = original_location[final_bracket_start+1:final_bracket_end].strip() if final_bracket_start!=-1 and final_bracket_end!=-1 else None
            city = potential_city if potential_city and potential_city not in location else None
    elif is_regular_address:
        bracket_start, bracket_end = web_location.find("["), web_location.find("]")
        if bracket_start!=-1 and bracket_end!=-1:
            bracketed_content = web_location[bracket_start+1:bracket_end].strip()
            location = web_location[:bracket_start].strip()
            if bracketed_content.upper().startswith("RP "):
                ramp_details = bracketed_content[3:].strip()
                if "/" in ramp_details:
                    parts = ramp_details.split("/")
                    second_part = parts[1].strip() if len(parts)>1 else ""
                    if " ENT " in second_part.upper() or second_part.upper().startswith("ENT "):
                        ent_pos = second_part.upper().find(" ENT ") if " ENT " in second_part.upper() else (0 if second_part.upper().startswith("ENT ") else -1)
                        if ent_pos!=-1:
                            before_ent = second_part[:ent_pos].strip() if ent_pos>0 else ""
                            after_ent = second_part[ent_pos:].strip() if ent_pos>0 else second_part
                            entrance_num = after_ent[4:].strip() if after_ent.upper().startswith("ENT ") else after_ent.split()[-1]
                            second_part = f"{before_ent} @ Entrance {entrance_num}" if before_ent else f"@ Entrance {entrance_num}"
                    elif " EXT " in second_part.upper() or second_part.upper().startswith("EXT "):
                        ext_pos = second_part.upper().find(" EXT ") if " EXT " in second_part.upper() else (0 if second_part.upper().startswith("EXT ") else -1)
                        if ext_pos!=-1:
                            before_ext = second_part[:ext_pos].strip() if ext_pos>0 else ""
                            after_ext = second_part[ext_pos:].strip() if ext_pos>0 else second_part
                            exit_num = after_ext[4:].strip() if after_ext.upper().startswith("EXT ") else after_ext.split()[-1]
                            second_part = f"{before_ext} Exit {exit_num}" if before_ext else f"Exit {exit_num}"
                    location = f"{location} Ramp & {second_part}"
                else:
                    location = f"{location} Ramp {ramp_details}"
                city = None
            else:
                city = bracketed_content
        else:
            location, city = web_location, None
    else:
        location, city = web_location, None
    words = location.split()
    for i, word in enumerate(words):
        upper = word.upper()
        if upper.startswith("MM") and upper[2:].isdigit() and is_highway_mm:
            if i>0 and words[i-1].upper() in("NB","SB","EB","WB","I-4","I-75","SR-54","US-41","SR-589"):
                words[i-1] += f" @ {word}"
                words[i] = ""
            elif i>=2 and ' '.join([words[i-2],words[i-1]]).lower() in['just south','just north','just east','just west']:
                words[i-2], words[i-1], words[i] = f"{words[i-2]} {words[i-1]} {word}", "", ""
            elif i>=1 and words[i-1].lower() in['south','north','east','west']:
                words[i-1], words[i] = f"{words[i-1]} {word}", ""
        elif upper in("NB","SB","EB","WB","SW","NW","SE","NE") or upper.startswith(("CR-","SR-","US-","I-")):
            words[i] = HIGHWAY_NAMES.get(upper,upper) if upper.startswith(("SR-","US-","I-","CR-")) else upper
        elif upper.startswith("MM") and len(upper)>2 and upper[2:].isdigit():
            words[i] = upper
        elif upper in("EXIT","ENTRANCE","RAMP"):
            words[i] = upper.title()
        elif word.lower() not in['just','south','north','east','west','of','crossroad'] and not re.match(r'^\d+(ST|ND|RD|TH)$',upper):
            words[i] = word.title()
    location = re.sub(r'\s+', ' ', re.sub(r'(NB|SB|EB|WB)\s*X\s*', r'\1 ', re.sub(r'X\s*@', '@', re.sub(r'\s+X\s+|^X\s+|\s+X$', ' ', " ".join(w for w in words if w))))).strip()
    return f"{location}, {city.title()}" if city and city.lower() not in location.lower() else location

def send_pushover_notification(title, message):
    response = requests.post("https://api.pushover.net/1/messages.json",data={"token":PUSHOVER_API_TOKEN,"user":PUSHOVER_USER_KEY,"title":title,"message":message})
    if DEBUG_MODE:
        print(f"{log_timestamp()} Notification {'sent' if response.status_code==200 else 'failed to send'}: {title}\n")
    if response.status_code!=200:
        print(f"Failed to send notification: {response.text}")

def fetch_incidents():
    try:
        response = requests.get(WEB_URL,headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text,'html.parser')
        update_panel = soup.find('span',{'id':'UpdatePanel2'})
        if not update_panel:
            return []
        rows = update_panel.find_all('tr',class_='dxgvDataRow')
        incidents = []
        for row in rows:
            cells = row.find_all('td',class_='dxgv')
            if len(cells)<9:
                continue
            county_cell = cells[4]
            link = county_cell.find('a')
            cad = None
            if link and 'onclick' in link.attrs:
                cad_match = re.search(r"popUP_MapInfo\('([^']+)'\)",link['onclick'])
                if cad_match:
                    cad = cad_match.group(1)
            if not cad:
                continue
            county = county_cell.get_text(strip=True)
            if FILTER_COUNTIES and county.upper() not in[c.upper() for c in FILTER_COUNTIES]:
                continue
            incidents.append({'cad':cad,'type':cells[0].get_text(strip=True),'reported':cells[1].get_text(strip=True),'lat':cells[7].get_text(strip=True),'lon':cells[8].get_text(strip=True),'county':county,'location':cells[5].get_text(strip=True),'remarks':cells[6].get_text(strip=True)})
        return incidents
    except Exception as e:
        print(f"Error fetching incidents: {e}")
        return []

def format_time(reported_time):
    try:
        dt = datetime.strptime(reported_time,"%m/%d/%Y %H:%M:%S")
        incident_hour = dt.hour
        if incident_hour==0:
            display_hour, am_pm = 12, "AM"
        elif incident_hour<12:
            display_hour = incident_hour
            am_pm = "PM" if datetime.now().hour>=12 else "AM"
        else:
            display_hour = 12 if incident_hour==12 else incident_hour-12
            am_pm = "PM"
        return f"{display_hour}:{dt.strftime('%M')} {am_pm}"
    except:
        return reported_time or "Unknown time"

def extract_incident_data(incident):
    remarks = incident['remarks'].title() if incident['remarks'] else ""
    if remarks:
        remarks = remarks.replace('&nbsp;','').strip()
        if("GMT" in remarks or any(m in remarks for m in["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]))and re.search(r'\b(GMT|UTC)\b|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b',remarks):
            remarks = ""
    return {"cad":incident['cad'],"type":format_incident_type(incident['type']),"location":clean_web_address(incident['location'])if incident['location']else"No location provided","remarks":remarks,"reported":format_time(incident['reported']),"map_link":f"https://maps.google.com/?q={incident['lat']},{incident['lon']}"if incident['lat']and incident['lon']else""}

def send_incident_notification(incident_data,is_update=False,previous_types=None,previous_locations=None,previous_remarks=None):
    title = f"UPDATE: {incident_data['type']}" if is_update else incident_data['type']
    msg = f"{'Previous Incident Type' if len(previous_types)==1 else 'Previous Incident Types'}: {', '.join(previous_types)}\n" if is_update and previous_types else ""
    msg += f"Location: {incident_data['location']}\n"
    msg += f"{'Previous Location' if len(previous_locations)==1 else 'Previous Locations'}: {', '.join(previous_locations)}\n" if is_update and previous_locations and len(previous_locations)>0 else ""
    msg += f"Remark: {incident_data['remarks'] if incident_data['remarks'] else 'No Remarks Provided'}\n"
    msg += f"{'Previous Remark' if len(previous_remarks)==1 else 'Previous Remarks'}: {', '.join(previous_remarks)}\n" if is_update and previous_remarks and len(previous_remarks)>0 else ""
    msg += f"Reported: {incident_data['reported']}\nMap: {incident_data['map_link']}"
    send_pushover_notification(title,msg)
    if DEBUG_MODE:
        remarks_text = incident_data['remarks'] if incident_data['remarks'] else "No Remarks Provided"
        print(f"{log_timestamp()} Information sent:\n{'New CAD Incident' if not is_update else 'CAD Incident'}: {incident_data['cad']}\nIncident Type: {incident_data['type']}")
        if is_update and previous_types:
            print(f"{'Previous Incident Type' if len(previous_types)==1 else 'Previous Incident Types'}: {', '.join(previous_types)}")
        print(f"Location: {incident_data['location']}")
        if is_update and previous_locations and len(previous_locations)>0:
            print(f"{'Previous Location' if len(previous_locations)==1 else 'Previous Locations'}: {', '.join(previous_locations)}")
        print(f"Remark: {remarks_text}")
        if is_update and previous_remarks and len(previous_remarks)>0:
            print(f"{'Previous Remark' if len(previous_remarks)==1 else 'Previous Remarks'}: {', '.join(previous_remarks)}")
        print(f"Reported: {incident_data['reported']}\nMap: {incident_data['map_link']}\n"+"-"*133)

def process_pending_notifications():
    current_time = datetime.now()
    to_notify = []
    for cad, pending in list(pending_incidents.items()):
        incident_data, is_update, last_remarks = pending["data"], pending["is_update"], pending["last_remarks"]
        if incident_data['remarks'] and incident_data['remarks']!=last_remarks:
            if DEBUG_MODE:
                print(f"{log_timestamp()} DEBUG: {'New CAD incident' if not is_update else 'CAD incident'}: {cad} - {'Updated remark added' if is_update else 'Remark added'}: '{incident_data['remarks']}'\n")
            to_notify.append(cad)
        elif current_time>=pending["wait_until"]:
            if DEBUG_MODE:
                remarks_status = "new remarks provided" if is_update and incident_data['remarks']!=last_remarks else("remarks provided" if incident_data['remarks']else"no remarks provided")
                print(f"{log_timestamp()} DEBUG: {'New CAD incident' if not is_update else 'CAD incident'}: {cad} - Wait time expired for {'update' if is_update else 'incident'}, {remarks_status}\n")
                if incident_data['remarks']:
                    remark_text = "Updated remark added" if is_update and incident_data['remarks']!=last_remarks else("Remark remained" if is_update else "Remark added")
                    print(f"{log_timestamp()} DEBUG: {'New CAD incident' if not is_update else 'CAD incident'}: {cad} - {remark_text}: '{incident_data['remarks']}'\n")
            to_notify.append(cad)
    for cad in to_notify:
        pending = pending_incidents[cad]
        incident_data, is_update = pending["data"], pending["is_update"]
        if is_update:
            record = sent_incidents[cad]
            previous_types = [record["type"]]+record.get("previous_types",[])
            previous_locations = record.get("previous_locations",[])if incident_data['location']!=record.get("location","")else None
            current_stored_remark = record.get("remark","")
            previous_remarks = None
            if incident_data['remarks']!=current_stored_remark:
                previous_remarks = record.get("previous_remarks",[])
                if current_stored_remark:
                    previous_remarks = [current_stored_remark]+previous_remarks
                if DEBUG_MODE and previous_remarks:
                    print(f"{log_timestamp()} DEBUG: CAD incident: {cad} - {'Previous remark' if len(previous_remarks)==1 else 'Previous remarks'}: {f'"{previous_remarks[0]}"' if len(previous_remarks)==1 else f'"{chr(34)+chr(44)+chr(32)+chr(34).join(previous_remarks)}"'}\n")
            send_incident_notification(incident_data,is_update=True,previous_types=previous_types,previous_locations=previous_locations,previous_remarks=previous_remarks)
            sent_incidents[cad]["previous_types"], sent_incidents[cad]["type"] = previous_types, incident_data['type']
            if incident_data['location']!=record.get("location",""):
                if "previous_locations" not in sent_incidents[cad]:
                    sent_incidents[cad]["previous_locations"] = []
                if record.get("location"):
                    sent_incidents[cad]["previous_locations"].insert(0,record["location"])
                sent_incidents[cad]["location"] = incident_data['location']
            if incident_data['remarks']!=record.get("remark",""):
                if "previous_remarks" not in sent_incidents[cad]:
                    sent_incidents[cad]["previous_remarks"] = []
                if record.get("remark"):
                    sent_incidents[cad]["previous_remarks"].insert(0,record["remark"])
                sent_incidents[cad]["remark"] = incident_data['remarks']
        else:
            send_incident_notification(incident_data,is_update=False)
            sent_incidents[cad] = {"type":incident_data['type'],"previous_types":[],"location":incident_data['location'],"previous_locations":[],"remark":incident_data['remarks'],"previous_remarks":[]}
        del pending_incidents[cad]

def process_incident(incident_raw):
    incident_data = extract_incident_data(incident_raw)
    if not incident_data:
        return
    cad, incident_type = incident_data["cad"], incident_data["type"]
    
    # Check if incident type is filtered (exact match only)
    is_filtered = False
    if FILTER_INCIDENT_TYPES:
        for filtered_type in FILTER_INCIDENT_TYPES:
            if filtered_type.lower() == incident_type.lower():
                is_filtered = True
                # Only show filter debug for new incidents (not preloaded) and only once per CAD
                if DEBUG_MODE and not preloaded.get(cad, False) and cad not in sent_incidents:
                   print(f"{log_timestamp()} DEBUG: Filtered incident type: {incident_type}\n" + "-"*133 + "\n")
                break
    
    # If this is a known incident that was previously filtered, check if it's now unfiltered
    if cad in sent_incidents and is_filtered:
        # Update the stored data but don't send notification
        if incident_data['location'] != sent_incidents[cad].get("location", ""):
            sent_incidents[cad]["location"] = incident_data['location']
        if incident_data['remarks'] != sent_incidents[cad].get("remark", ""):
            sent_incidents[cad]["remark"] = incident_data['remarks']
        return
    
    # If newly filtered, mark it as sent so we can track if it changes to unfiltered later
    if is_filtered and cad not in sent_incidents:
        sent_incidents[cad] = {"type":incident_type,"previous_types":[],"location":incident_data['location'],"previous_locations":[],"remark":incident_data['remarks'],"previous_remarks":[]}
        return
    if cad in sent_incidents:
        record = sent_incidents[cad]
        if incident_type!=record["type"]:
            type_change_key = f"{cad}_{record['type']}_to_{incident_type}"
            if type_change_key not in type_change_logged:
                if DEBUG_MODE:
                    print(f"{log_timestamp()} DEBUG: CAD incident: {cad} - Incident type changed from '{record['type']}' to '{incident_type}'\n")
                    if incident_data['location']!=record.get("location",""):
                        print(f"{log_timestamp()} DEBUG: CAD incident: {cad} - Raw location: {' '.join(incident_raw['location'].split())}\n{log_timestamp()} DEBUG: CAD incident: {cad} - Formatted location: {incident_data['location']}\n{log_timestamp()} DEBUG: CAD incident: {cad} - New location: {incident_data['location']}\n")
                    else:
                        print(f"{log_timestamp()} DEBUG: CAD incident: {cad} - No updates on location\n")
                type_change_logged[type_change_key] = True
            if cad in pending_incidents:
                pending_incidents[cad]["data"] = incident_data
            else:
                pending_incidents[cad] = {"data":incident_data,"wait_until":datetime.now()+timedelta(seconds=UPDATE_WAIT_TIME),"is_update":True,"last_remarks":sent_incidents[cad].get("remark","")}
                if DEBUG_MODE:
                    print(f"{log_timestamp()} DEBUG: CAD incident: {cad} - Added to pending updates, waiting {UPDATE_WAIT_TIME} seconds for updated remark\n")
        elif cad in sent_incidents:
            if incident_data['location']!=sent_incidents[cad].get("location",""):
                sent_incidents[cad]["location"] = incident_data['location']
            if incident_data['remarks']!=sent_incidents[cad].get("remark",""):
                sent_incidents[cad]["remark"] = incident_data['remarks']
    else:
        if not preloaded.get(cad,False):
            if cad in pending_incidents:
                pending_incidents[cad]["data"] = incident_data
            else:
                pending_incidents[cad] = {"data":incident_data,"wait_until":datetime.now()+timedelta(seconds=NEW_INCIDENT_WAIT_TIME),"is_update":False,"last_remarks":""}
                if DEBUG_MODE:
                    print(f"{log_timestamp()} DEBUG: New CAD incident: {cad} - New incident added to pending, waiting {NEW_INCIDENT_WAIT_TIME} seconds for remark\n")
                    print(f"{log_timestamp()} DEBUG: New CAD incident: {cad} - Raw location: {' '.join(incident_raw['location'].split())}\n")
                    print(f"{log_timestamp()} DEBUG: New CAD incident: {cad} - Formatted location: {incident_data['location']}\n")
        else:
            sent_incidents[cad] = {"type":incident_type,"previous_types":[],"location":incident_data['location'],"previous_locations":[],"remark":incident_data['remarks'],"previous_remarks":[]}

def main():
    print("\nStarting FHP Traffic Incident Notifier V1 - Developed by Ryan Watern\n")
    print(f"Counties: {', '.join(FILTER_COUNTIES)}\nCheck interval: {CHECK_INTERVAL} seconds\nNew incident remark wait time: {NEW_INCIDENT_WAIT_TIME} seconds\nUpdate remark wait time: {UPDATE_WAIT_TIME} seconds\nDebug mode: {'ON' if DEBUG_MODE else 'OFF'}\n"+"-"*133+"\nPreloading existing incidents...\n")
    for incident in fetch_incidents():
        incident_data = extract_incident_data(incident)
        if incident_data:
            cad = incident_data["cad"]
            preloaded[cad] = True
            sent_incidents[cad] = {"type":incident_data["type"],"previous_types":[],"location":incident_data['location'],"previous_locations":[],"remark":incident_data['remarks'],"previous_remarks":[]}
    if DEBUG_MODE:
        print(f"{log_timestamp()} DEBUG: Preloaded {len(preloaded)} existing incidents")
    print("\nMonitoring for new incidents and updates...\n"+"-"*133)
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


