# FHP Traffic Incident Notifier
A real-time notification system that monitors the Florida Highway Patrol Live Traffic Crash and Road Condition Report source code for all incidents across Florida. It delivers alerts with location, remarks, and report time, logs all CAD calls, and provides follow-up notifications for updated incident types while showing previous incident types, locations and remarks. The system also standardizes location data and generates Google Maps links for precise incident locations. *This system is an independent project and is not affiliated with or endorsed by the Florida Highway Patrol (FHP)*.
<div align="center">
  <img src="Images/8121a837-ab51-42c5-83d4-fb8e4e3b596e.jpg" width="250" />
  <img src="Images/82720532-efb0-466e-83ef-14fce39ea960.jpg" width="250" />
  <img src="Images/3b04e200-2650-4084-806a-a99393b42c1d.jpg" width="250" />
</div>

<br>
<div align="center">
  <img src="Images/Screenshot%202025-10-07%20234144.png width="400" />
  <img src="Images/Screenshot%202025-10-08%20024223.png" width="400" />
</div>

# Running the Script

To run this script, first install Python, ensuring that you check the box labeled “Add Python to PATH” during installation.
After installation, open the Command Prompt and enter the following commands one at a time:
	1.	pip install requests.
Press Enter and wait for the installation to complete.
	2.	pip install beautifulsoup4.
Press Enter again and wait until the installation finishes.

Once both libraries have been installed, open the script in Notepad (or any text editor) and configure it according to your preferences. Make sure to enter your Pushover User Key and API Token in the designated fields.

When configuration is complete, return to the Command Prompt, navigate to the folder containing the script, and run it by typing:
python FHP_Traffic_Notifier_V1.py



# Getting Started with Notifications

To begin receiving notifications on your phone, download the Pushover application and create an account. Once your account is set up, you will receive both a User Key and an API Token. These credentials must be entered into the script to enable notifications.


# Filtering Notifications

To filter notifications by county, edit the FILTERED_COUNTIES section. Include only the counties from which you wish to receive notifications.
For example, to receive notifications exclusively for Pasco County, you would enter:
[Pasco]

This process differs from filtering incident types. To exclude specific incident types, list them in the FILTERED_INCIDENTS section. The names must match exactly as they appear on the official FHP page for the filter to work properly.
For example, if you do not wish to receive notifications for Vehicle Crashes that involve no injuries or roadblocks, enter:
[Vehicle Crash]

Note: If an incident updates to a type that is not filtered, you will still receive the update notification, which will include the previous incident type.


# Road Mapping

If you want abbreviated road names to display as their full versions in notifications, edit the HIGHWAY_NAMES section.
For example, to display “US-19” as “US Highway 19,” you would enter:
'US-19': 'US Highway 19'
Additional mappings should be added after a comma.


# Important Note

Not all locations will display perfectly. While most are formatted correctly, some may appear partially incorrect if the FHP report contains inconsistent or improperly formatted data. If you notice recurring errors within your subscribed county, you can correct them manually within the CLEAN_WEB_ADDRESS section.
