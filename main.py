import requests
from bs4 import BeautifulSoup
import re
import os
from pprint import pprint
from getpass import getpass
import pyautogui

def sfp_tt3_log_request(jobid, username, password):
    "Retrieve SFP data from the the user-provided jobID list by making a request to TT3 \
    The SFP data will only come from the first corner of each JobID \
    then filter out all the unnecessary text then print out the table format"

    file_list = []
    first_cornerID, total_corner, total_uut = find_first_corner(jobid, username, password)

    # Request SFP data from the first CornerID
    sfpeeprom_csv_file = f"{jobid}_{first_cornerID}_SFEEPROM.csv"
    working_directory = str(os.getcwd())
    url = f"https://wwwin-testtracker3.cisco.com/trackerApp/oneviewlog/opticalData.csv?page=1&corner_id={first_cornerID}"

    # 1. Send HTTP Request with TT3 credentials
    response = requests.get(url, auth=(username, password))
    response.close()

    # 2. Use BeautifulSoup to extract text
    html = response.text
    soup = BeautifulSoup(html, features='html.parser')
    for script in soup(["script", "style"]):
        script.extract()
    text = soup.get_text()
    # Strip out space and double space
    lines = (line.strip() for line in text.splitlines())
    # Fix strange character from various sfp type
    lines = (line.replace("  (", " (") for line in lines)
    lines = (line.replace("],", ",") for line in lines)
    lines = (line.replace(",INC,", ",") for line in lines)
    lines = (line.replace(",0x10  -- unrecognized compliance code.,", ",0x10 unrecognized,") for line in lines)
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = '\n'.join(chunk for chunk in chunks if chunk)

    # Strip off unnecessary text but keep SFPEEPROM data table
    stri = text[text.index('+++'):text.index('Show\n')]
    sections = re.split(r"\s*\+{10,}\s*", stri)
    # To strip blank element
    section_headers = [section.strip() for section in sections if section.strip()]

    for header in section_headers[::2]:
        # table_list.append(header)
        # Generate CSV file for SFEEPROM only
        if header == "SFEEPROM":
            table_name_file = os.path.join(working_directory, sfpeeprom_csv_file)
            file_list.append(table_name_file)

    # pprint(file_list)
    # Map header and date into the generated csv file
    # writing sfp table  into a csv file
    for header, section_data in zip(section_headers[::2], section_headers[1::2]):
        for i in range(0, len(file_list)):
            if header in file_list[i]:
                # print('separating', header, 'table into a file')
                # file = open(file_list[i], "a")
                file = open(file_list[i], "w")
                file.write('+' * 35 + ' ' + header + ' ' + '+' * 35 + '\n')
                file.write(section_data)
                file.close()
    file_list = []

    # print(sfpeeprom_csv_file)
    return sfpeeprom_csv_file, total_corner, total_uut

def create_list_dict_sfp(sfpeeprom_csv_file, total_corner, unit):

    with open(sfpeeprom_csv_file, 'r') as input_file:
        lines = input_file.readlines()
        # print(lines)
        lines = lines[2:]
        # print(lines)

    # comment below line if also need to keep csv file
    # os.remove(sfpeeprom_csv_file)

    # Read each line and keep key value in a list of dictionaries
    # then loop through a list of uut through dictionary key
    uut_list = []
    list_of_port_dict = []
    for line in lines:
        if "switch" + unit in line:
            s = {}
            (s["jobid"], s["cornerid"], s["uut"], s["port"], s["type"], s["vendor"], s["mfg"], s["sn"], s["create"],
             s["create_date"], s["update"], s["update_date"], s["slot"]) = line.split(",")

            # To add s["pid"] here
            # add a function to find pid from mfg number
            s["pid"] = find_pid_by_mfg(s["mfg"])
            s["port"] = s["port"].zfill(2)

            # list_of_port_dict.append(s)

            # This part is database mapping to find out type from mfg partnumber
            # print(s["type"])
            if s["type"] == "Data unavailable" or s["type"] == "0x0 (Non Standard)" or s["type"] == "0x80 (Unknown)" or \
                    s["type"] == "0x10 unrecognized":
                s["type"] = find_type_by_mfg(s["mfg"])
            else:
                s["type"] = re.search(r"\((.*?)\)", s["type"]).group(1)
                # TRY OVERWRITE TYPE IF MFG AVAILABLE IN DATABASE
                s["type"] = find_type_by_mfg(s["mfg"])

            if (s['type'], s['vendor'], s['mfg'], s['pid']) not in sfp_type_result:
                sfp_type_result.append((s['type'], s['vendor'], s['mfg'], s['pid']))

            list_of_port_dict.append(s)

    input_file.close()
    # print("from create_list_dict_sfp", list_of_port_dict)
    return list_of_port_dict, sfp_type_result

def find_first_corner(jobid, username, password):
    "Find the first corner ID from the user-provided jobID list by making a request to TT3 \
    then filter out all the unnecessary text then return the first cornerID"

    url = f"https://wwwin-testtracker3.cisco.com/trackerApp/cornerTest/{jobid}"

    # 1. Send HTTP Request with TT3 credentials
    response = requests.get(url, auth=(username, password))
    response.close()

    # 2. Use BeautifulSoup to extract text
    html = response.text

    total_corner = extract_total_corner(html)
    total_uut = extract_total_uut(html)

    soup = BeautifulSoup(html, features='html.parser')
    for script in soup(["script", "style"]):
        script.extract()
    text = soup.get_text()

    # Fix double space has issue
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = '\n'.join(chunk for chunk in chunks if chunk)

    # Remove all the other sting but first cornerID
    stri = text[text.index('Select Corners to delete:'):text.index(
        '* Press Submit to Delete the Corners, Cancel to Return')]
    cornerID_list = list(stri.split('\n'))
    cornerID_list.remove('Select Corners to delete:')
    first_CornerID = cornerID_list[0]

    return first_CornerID, total_corner, total_uut

def find_type_by_mfg(lookup_mfg):
    input_file = open('SFPs_Database.csv')
    for line in input_file:
        data = {}
        (data['type'], data['vendor'], data['mfg'], data['pid'], data['sn']) = line.split(',')
        if data['mfg'] == lookup_mfg:
            input_file.close()
            return data["type"]
    input_file.close()
    return "Not in Database"

def find_pid_by_mfg(lookup_mfg):
    input_file = open('SFPs_Database.csv')
    for line in input_file:
        data = {}
        # print(line) # Debug not enough values to unpack.
        # Most of the time caused from extra blank line in SFP database txt file
        (data['type'], data['vendor'], data['mfg'], data['pid'], data['sn']) = line.split(',')
        if data['mfg'] == lookup_mfg:
            input_file.close()
            return data["pid"]
    input_file.close()
    return "Not in Database"

def extract_total_uut(html):
    uut_match = re.findall(r'UUT\d+ </span></td>', html)
    total_uut = []

    for match in uut_match:
        uut_id = re.search(r'\d+', match).group(0)
        if uut_id not in total_uut:
            total_uut.append(uut_id)
    return total_uut

def extract_total_corner(html):
    corner_match = re.findall(r'data-cornerid="\d+"', html)
    total_corner = []

    for match in corner_match:
        corner_id = re.search(r'\d+', match).group(0)
        if corner_id not in total_corner:
            total_corner.append(corner_id)
    return total_corner

def check_sfp_diag_traffic(jobid, corner, uut, username, password):

    result = []

    url = f"https://wwwin-testtracker3.cisco.com/trackerApp/oneviewlog/switch{uut}.log?page=1&corner_id={corner}"
    print(f'\nJobID:{jobid} CornerID:{corner} switch{uut}\n{url}')

    response = requests.get(url, auth=(username, password))
    response.close()
    html_log = response.text

    # Create a local log file
    html_log_name = f"{jobid}_{corner}_uut{uut}_html_log.txt"
    # print(html_log_name)
    data = {"cornerid": corner, "uut": uut, "logfile": html_log_name, "failures": [], "uutinfo": []}
    result.append(data)
    content = html_log[html_log.index("TESTCASE START"):html_log.index(f"{corner} Complete")]

    # To add option if need a local html log
    with open(html_log_name, "w") as local_log:
        local_log.write(content)

    # for i in range(len(result)):
    for item in result:
        # print(item["logfile"])
        f = open(item["logfile"], "r")
        text = f.read()
        content = text[text.index("TESTCASE START"):text.index("Corner - runSwitch")]
        lines = content.splitlines()
        for line in lines:
            if "SYSTEM_SERIAL_NUM" in line:
                if line not in item['uutinfo']:
                    item['uutinfo'].append(line.strip())

            # SEARCH FOR FAILED PORTS
            if re.search(r'FAIL\*\*\s+[a-zA-Z]', line):
                data = {}
                if line not in item['failures']:
                    item['failures'].append(line)
        f.close()
    os.remove(item["logfile"])

    # Find failed traffic combination
    traf_failures = []
    traffic_failed_combination_list = []

    for item in result:
        switch_number = 'switch' + item['uut']

        for info in item['uutinfo']:
            if "SYSTEM_SERIAL" in info:
                serial_number = info
                print(f"{serial_number}")

        for failure in item['failures']:
            # print(failure)
            if "Ext" in failure:
                data = {}
                (data['conver'], data['portpair'], data['iter'], data['duration'], data['status'], data['error'],
                 data['duration'], data['portresult'], data['traftype'], data['speed'], data['size']) = failure.split()
                traf_failures.append(data)

    for item in traf_failures:
        for key in ["conver", "iter", "duration", "status", "portresult"]:
            item.pop(key)
        if item not in traffic_failed_combination_list:
            traffic_failed_combination_list.append(item)

    # Find failed portpair and convert into single port list
    fail_portpair = []
    fail_port_single = []
    for item in traffic_failed_combination_list:
        if item["portpair"] not in fail_portpair:
            fail_portpair.append(item["portpair"])

            # To create a new list with a single port to map with the SFP list in the future
            first_port, second_port = item["portpair"].split('/')
            if first_port not in fail_port_single or second_port not in fail_port_single:
                fail_port_single.append(first_port.zfill(2))
                fail_port_single.append(second_port.zfill(2))
    fail_port_single.sort()

    # Find failed speeds - for future report
    fail_speed = []
    for item in traffic_failed_combination_list:
        if item["speed"] not in fail_speed:
            fail_speed.append(item["speed"])
    # print("failed speeds are : ", *fail_speed, sep='\n\t')

    # Find failed sizes - for future report
    fail_size = []
    for item in traffic_failed_combination_list:
        if item["size"] not in fail_size:
            fail_size.append(item["size"])
    # print("failed size are : ", *fail_size, sep='\n\t')

    return fail_port_single

def print_sfp_result(list_of_port_dict, failed_port_single, sfp_file_result, jobid, corner, uut):
    class bcolors:
        HEADER = '\033[95m'
        OKBLUE = '\033[94m'
        OKCYAN = '\033[96m'
        OKGREEN = '\033[92m'
        WARNING = '\033[93m'
        FAIL = '\033[91m'
        ENDC = '\033[0m'
        BOLD = '\033[1m'
        UNDERLINE = '\033[4m'


    # Add to write result in file
    with open(sfp_file_result, "a") as sfp_file_result:

        # print(f'JobID:{jobid} CornerID:{corner} switch{uut}')
        sfp_file_result.write('\n' + f'JobID:{jobid} CornerID:{corner} switch{uut}' + '\n')

        print(f'{bcolors.BOLD}{bcolors.OKBLUE}-{bcolors.ENDC}' * 150)
        sfp_file_result.write('-' * 150 + '\n')

        print(
            f'{bcolors.BOLD}{bcolors.OKBLUE}{"port":<10} {"sfp_type":<20} {"Cisco PID":<20} {"sfp_vendor":<20} {"mfg_number":<20} {"serial_number":<20} {"port_result"}{bcolors.ENDC}')
        sfp_file_result.write(f'{"port":<10} {"sfp_type":<20} {"Cisco PID":<20} {"sfp_vendor":<20} {"mfg_number":<20} {"serial_number":<20} {"port_result"}' + '\n')

        print(f'{bcolors.BOLD}{bcolors.OKBLUE}-{bcolors.ENDC}' * 150)
        sfp_file_result.write('-' * 150+ '\n')

        for item in list_of_port_dict:
            # print("item", item)
            item.update(port_result="pass")

            for failed_port in failed_port_single:
                if item["port"] == failed_port:
                    item.update(port_result="fail")

            if item["port_result"] == "fail":
                print(
                    f'{bcolors.FAIL}{item["port"].strip("]"):<10} {item["type"]:<20} {item["pid"]:<20} {item["vendor"]:<20} {item["mfg"]:<20} {item["sn"]:<20} {item["port_result"]:<20}{bcolors.ENDC}')
                sfp_file_result.write(f'{item["port"].strip("]"):<10} {item["type"]:<20} {item["pid"]:<20} {item["vendor"]:<20} {item["mfg"]:<20} {item["sn"]:<20} {item["port_result"]} ***' + "\n")
            else:
                print(
                    f'{bcolors.OKGREEN}{item["port"].strip("]"):<10} {item["type"]:<20} {item["pid"]:<20} {item["vendor"]:<20} {item["mfg"]:<20} {item["sn"]:<20} {item["port_result"]:<20}{bcolors.ENDC}')
                sfp_file_result.write(f'{item["port"].strip("]"):<10} {item["type"]:<20} {item["pid"]:<20} {item["vendor"]:<20} {item["mfg"]:<20} {item["sn"]:<20} {item["port_result"]:<20}' + '\n')

    sfp_file_result.close()
###############################

if __name__ == '__main__':

    jobids = input('single or multiple jobids separate by comma: ')
    username = pyautogui.prompt('input your cec username: ')
    password = pyautogui.password('input your password: ')

    jobID_list = []
    for i in jobids.split(','):
        jobID_list.append(i.strip())
    print("USER INPUT: ", jobID_list)

    sfp_type_result = []

    for jobid in jobID_list:
        sfpeeprom_csv_file, total_corner, total_uut = sfp_tt3_log_request(jobid, username, password)

        for uut in total_uut:
            sfp_file_result = f'{jobid}_switch{uut}_sfp_result.txt'

            for corner in total_corner:
                    list_of_port_dict, sfp_type_result = create_list_dict_sfp(sfpeeprom_csv_file, total_corner, uut)
                    print(f"\nPROCESSING ON JOBID: {jobid} CORNERID: {corner} UNIT: {uut}")
                    fail_port_single = check_sfp_diag_traffic(jobid, corner, uut, username, password)

                    # print_sfp_result(list_of_port_dict, fail_port_single)
                    print_sfp_result(list_of_port_dict, fail_port_single, sfp_file_result, jobid, corner, uut)


    # PRINT TEXT SUMMARY
    # print("\n----------------------------------")
    # print(f"RESULT THERE ARE TOTAL {len(sfp_type_result)} VARIATIONS")
    # print("----------------------------------")
    # for index, item in enumerate(sfp_type_result):
    #     print(f"\nITEM# {index}")
    #     print("----------------------------------")
    #     item_list = list(item)
    #     print("TYPE: " + item_list[0])
    #     print("VENDOR: " + item_list[1])
    #     print("MFG PARTNUM: " + item_list[2])
    #     print("CISCO PID: " + item_list[3])

    # PRINT CSV SUMMARY
    print("\n----------------------------------")
    print(f"RESULT THERE ARE TOTAL {len(sfp_type_result)} VARIATIONS")
    print("----------------------------------")

    print(f'NO,TYPE,PID,VENDOR,MFG_PARTNUM')
    for index, item in enumerate(sfp_type_result, 1):
        item_list = list(item)
        print(f'{index},{item_list[0]},{item_list[3]},{item_list[1]},{item_list[2]}')
