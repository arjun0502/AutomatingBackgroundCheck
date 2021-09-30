from flask import Flask, Blueprint, request, Response
import xmltodict
import requests
import json
from simple_salesforce import Salesforce, SFType, SalesforceLogin
import boto3
from boto3.dynamodb.conditions import Key, Attr
from threading import Thread
import xml.etree.ElementTree as ET
from settings import settings

app = Blueprint('backgroundCheck', __name__, template_folder='templates')
@app.route('/background-check', methods=['POST'])

def main():
   ## Parses Salesforce outbound message after 'Request Background Check' trigger activated for Salesforce lead
   ## If invalid Organization ID detected, returns acknowledgement to Salesforce outbound message and exits main() 
   ## Else, retrieves Salesforce lead ID and dictionary containing lead PII 
   return_tuple = parse_sf_outbound_msg()
   invalid_org_id = return_tuple[2]
   if invalid_org_id == True:
      print("Returning acknowledgement to Salesforce outbound message")
      sf_outbound_msg_acknowledgement = get_sf_outbound_msg_acknowledgement()
      return sf_outbound_msg_acknowledgement
   else:
      salesforce_lead_ID = return_tuple[0]
      salesforce_lead_PII_dict = return_tuple[1]
      
   ## Creates Checkr candidate for Salesforce lead with corresponding lead ID and lead PII
   ## If error occured in create_checkr_candidate(), returns acknowledgement to Salesforce outbound message and exits main()
   ## Else, retrieves Checkr candidate ID 
   return_tuple_candidate = create_checkr_candidate(salesforce_lead_ID, salesforce_lead_PII_dict)
   error_occured = return_tuple_candidate[1]
   if error_occured == True:
      print("Returning acknowledgement to Salesforce outbound message")
      sf_outbound_msg_acknowledgement = get_sf_outbound_msg_acknowledgement()
      return sf_outbound_msg_acknowledgement
   else:
      checkr_candidate_ID = return_tuple_candidate[0]      
   
   ## Creates Checkr report for Checkr candidate with corresponding candidate ID
   create_checkr_report(checkr_candidate_ID)
   
   ## Returns acknowledgement to Salesforce outbound message and exits main()
   sf_outbound_msg_acknowledgement = get_sf_outbound_msg_acknowledgement()
   return sf_outbound_msg_acknowledgement         
   


"""
Parses Salesforce outbound message after 'Request Background Check' trigger activated for Salesforce lead
Parameters: None
Output: lead ID, dictionary containing lead PII (Personally Identifiable Information), and 'invalid_org_id' boolean indicating whether invalid Organization ID detected
"""
def parse_sf_outbound_msg():
   outbound_msg_dict = xmltodict.parse(request.data)
   
   ## Retrieves Salesforce Organization ID from outbound message and checks whether it matches Morning Star Foundation's Organization ID
   ## This prevents someone from outside Morning Star Foundation running the background check process
   organizationID = outbound_msg_dict["soapenv:Envelope"]["soapenv:Body"]['notifications']['OrganizationId']
   ## If organization ID is invalid, sets 'invalid_org_id' to True, puts in placeholders for 'salesforce_lead_ID' and 'salesforce_lead_PII_dict', and returns all three fields
   if organizationID != settings.salesforceOrgID:
      print("Invalid Organization ID")
      invalid_org_id = True
      salesforce_lead_ID = ''
      salesforce_lead_PII_dict = {}
      return salesforce_lead_ID, salesforce_lead_PII_dict, invalid_org_id      
   else:
      print("Valid Organization ID")

   ## Retrieves Salesforce lead ID and PII from outbound message
   print("")
   print("Salesforce Lead")
   lead_dict = outbound_msg_dict["soapenv:Envelope"]["soapenv:Body"]['notifications']['Notification']['sObject']
   salesforce_lead_ID = lead_dict["sf:Id"]
   print("lead ID: " + salesforce_lead_ID)
   first_name = lead_dict["sf:FirstName"]
   print("first name: " + first_name)
   no_middle_name = bool(lead_dict["sf:no_middle_name__c"])
   middle_name = None
   if no_middle_name == False:
      middle_name = lead_dict["sf:MiddleName"]
   print("middle_name: " + str(middle_name))
   last_name = lead_dict["sf:LastName"]
   print("last name: " + last_name)
   email = lead_dict["sf:Email"]
   zipcode = lead_dict["sf:PostalCode"][0:5]
   dob =  lead_dict["sf:Birthdate__c"]
   ssn = lead_dict["sf:SSN__c"]
   phone = lead_dict["sf:Phone"]

   ## Creates dictionary containing Salesforce lead PII
   salesforce_lead_PII_dict = {'first_name':first_name,'no_middle_name':no_middle_name,'middle_name':middle_name,'last_name':last_name,'email':email,
                               'zipcode':zipcode,'dob':dob,'ssn':ssn,'phone':phone}
   
   ## Set 'invalid_org_id' field to False and returns it along with lead ID and dictionary containing lead PII    
   invalid_org_id = False
   return salesforce_lead_ID, salesforce_lead_PII_dict, invalid_org_id


"""
Creates Checkr candidate for Salesforce lead with corresponding lead ID and lead PII
Parameters: Salesforce lead ID and dictionary containing Salesforce lead PII
Output: Checkr candidate ID and 'error_occured' boolean indicating whether error has occured
"""
def create_checkr_candidate(salesforce_lead_ID, salesforce_lead_PII_dict):
   ## Queries Salesforce lead ID in DynamoDB table to check if Checkr candidate has already been created for Salesforce lead
   dynamodb = boto3.resource('dynamodb')
   background_check_table = dynamodb.Table(settings.backgroundCheckTable)
   print("")
   print("Querying DynamoDB table to see if Checkr candidate has already been created for Salesforce lead (lead_ID: " + salesforce_lead_ID + ")")
   lead_ID_query = background_check_table.scan(FilterExpression=Attr('salesforce_lead_ID').eq(salesforce_lead_ID))
   
   ## If Checkr candidate already exists for Salesforce lead, creates a Salesforce 'Background Check' object with error for given lead
   ## Then sets 'error_occured' to True, puts in placeholder for 'checkr_candidate_ID', and returns both fields
   if lead_ID_query['Count'] != 0:
      print("Checkr candidate has already been created for Salesforce lead (lead_ID: " + salesforce_lead_ID + ")")
      print(lead_ID_query['Items'])
      ### Gets 'Background Check' object payload for given Salesforce lead and updates it with error and 'incomplete' background check status
      salesforce_lead_name = salesforce_lead_PII_dict['first_name'] + ' ' + salesforce_lead_PII_dict['last_name']
      BC_object_error_payload = get_BC_object_payload(salesforce_lead_ID, salesforce_lead_name)
      BC_object_error_payload['Error_Create_Candidate__c'] = "Checkr candidate already created"
      BC_object_error_payload['Status_Background_Check__c'] = 'incomplete'
      ### Creates a Salesforce 'Background Check' object with error for given lead by making call to Salesforce REST API
      call = sf_api_call("/services/data/v49.0/sobjects/Background_Check__c", method = "post", data = BC_object_error_payload)      
      BC_object_id = call.get('id')
      print("Created Background Check object (" + BC_object_id + ") for Salesforce lead containing error")            
      ### Sets 'error_occured' to True, puts in placeholder for 'checkr_candidate_ID', and returns both fields
      error_occured = True
      checkr_candidate_ID = ''
      return checkr_candidate_ID, error_occured
   else:
      print("Checkr candidate does not exist for Salesforce lead (lead_ID: " + salesforce_lead_ID + ")")

   ## Creates a Checkr candidate for Salesforce lead through POST request to Checkr API
   print("")
   print("Creating Checkr candidate for Salesforce lead (lead_ID: " + salesforce_lead_ID + ")")
   create_candidate_response =  requests.post(url = settings.checkrBaseUrl + '/v1/candidates', auth = (settings.checkrApiKey, ''), data = salesforce_lead_PII_dict)
   candidate_object = create_candidate_response.json()
   create_candidate_response.close()
   
   ## If error with creating Checkr candidate, creates a Salesforce 'Background Check' object with error for given lead
   ## Then sets 'error_occured' to True, puts in placeholder for 'checkr_candidate_ID', and returns both fields   
   if create_candidate_response.ok == False:
      ### Retrieves error
      error_create_candidate = candidate_object["error"][0]
      print("Error in creating Checkr candidate: " + error_create_candidate)
      ### Gets 'Background Check' object payload for given Salesforce lead and updates it with error and 'incomplete' background check status
      salesforce_lead_name = salesforce_lead_PII_dict['first_name'] + ' ' + salesforce_lead_PII_dict['last_name']
      BC_object_error_payload = get_BC_object_payload(salesforce_lead_ID, salesforce_lead_name)
      BC_object_error_payload['Error_Create_Candidate__c'] = error_create_candidate
      BC_object_error_payload['Status_Background_Check__c'] = 'incomplete'
      ### Creates a Salesforce 'Background Check' object with error for given lead by making call to Salesforce REST API
      call = sf_api_call("/services/data/v49.0/sobjects/Background_Check__c", method = "post", data = BC_object_error_payload)
      BC_object_id = call.get('id')
      print("Created Background Check object (" + BC_object_id + ") for Salesforce lead containing error")            
      ## Sets 'error_occured' to True, puts in placeholder for 'checkr_candidate_ID', and returns both fields
      error_occured = True
      checkr_candidate_ID = ''
      return checkr_candidate_ID, error_occured
   else:
      print("No errors in creating Checkr candidate")

   ## Retrieves ID of Checkr candidate
   checkr_candidate_ID = candidate_object["id"]
   print("Checkr candidate ID: " + checkr_candidate_ID)

   ### Creates new item in DynamoDB table for Checkr candidate
   print("")
   print("Creating new item in DynamoDB table for Checkr candidate (candidate_ID: " + checkr_candidate_ID + ")")
   background_check_table.put_item(Item={'name': salesforce_lead_PII_dict['first_name'] + ' ' + salesforce_lead_PII_dict['last_name'], 'salesforce_lead_ID': salesforce_lead_ID, 
                                         'checkr_candidate_ID': checkr_candidate_ID, 'checkr_report_ID': '', 'checkr_status': "candidate created"})
   
   ## Sets 'error_occured' field to False and returns it along with checkr candidate ID    
   error_occured = False
   return checkr_candidate_ID, error_occured


"""
Creates Checkr report for Checkr candidate with corresponding candidate ID
Parameters: Checkr candidate ID
Output: None
"""
def create_checkr_report(checkr_candidate_ID):
   ## Gets Salesforce lead name and lead ID for given Checkr candidate ID in DynamoDB table
   dynamodb = boto3.resource('dynamodb')
   background_check_table = dynamodb.Table(settings.backgroundCheckTable)
   candidate_ID_query = background_check_table.scan(FilterExpression=Attr('checkr_candidate_ID').eq(checkr_candidate_ID))
   salesforce_lead_name = candidate_ID_query['Items'][0]['name']
   salesforce_lead_ID = candidate_ID_query['Items'][0]['salesforce_lead_ID']
   
   ## Creates Checkr report for given Checkr candidate with corresponding candidate ID
   print("")
   print("Creating Checkr report for candidate (candidate_ID: " + checkr_candidate_ID + ")")
   payload = {'package' : settings.checkrPackage, 'candidate_id' : checkr_candidate_ID}
   create_report_response =  requests.post(url = settings.checkrBaseUrl + '/v1/reports', auth = (settings.checkrApiKey, ''), data = payload)
   report_object = create_report_response.json()
   create_report_response.close()
   ## If error in creating Checkr report, creates a Salesforce 'Background Check' object with error for given lead, and returns acknowledgement to Salesforce outbound message
   if create_report_response.ok == False:
      ### Retrieves error
      error_create_report = report_object['error'][0]
      print("Error in creating Checkr report: " + error_create_report)
      ### Creates 'Background Check' object payload for given Salesforce lead and updates it with error and incomplete 'background_check' status
      BC_object_error_payload = get_BC_object_payload(salesforce_lead_ID, salesforce_lead_name)
      BC_object_error_payload['Error_Create_Report__c'] = error_create_report
      BC_object_error_payload['Status_Background_Check__c'] = 'incomplete'
      ### Creates a Salesforce 'Background Check' object with error for given lead
      call = sf_api_call("/services/data/v49.0/sobjects/Background_Check__c", method = "post", data = BC_object_error_payload)
      BC_object_id = call.get('id')
      print("Created Background Check object (" + BC_object_id + ") for Salesforce lead containing error")      
      ## Return acknowledgement to Salesforce outbound message
      sf_outbound_msg_acknowledgement = get_sf_outbound_msg_acknowledgement()
      return sf_outbound_msg_acknowledgement  
   else:
      print("No errors in creating report")

   ## Retrieves Checkr report ID
   checkr_report_ID = report_object['id']
   print("checkr_report_ID: " + checkr_report_ID)

   ## Updates report ID and status for Checkr candidate in DynamoDB table
   dynamodb = boto3.resource('dynamodb')
   background_check_table = dynamodb.Table(settings.backgroundCheckTable)
   print("")
   print("Updating report ID and status for Checkr candidate (candidate_ID: " + checkr_candidate_ID + ")" " in DynamoDB table")
   response = background_check_table.update_item(
    Key={'salesforce_lead_ID': salesforce_lead_ID},
    UpdateExpression="set checkr_status=:v1, checkr_report_ID=:v2",
    ExpressionAttributeValues={
        ':v1': "report created",
        ':v2': checkr_report_ID
    },
    ReturnValues="UPDATED_NEW"
   )

   return Response(status = 200)


"""
Retrieves Checkr report and creates Salesforce 'Background Check' object with report results for Salesforce lead
Input: Checkr report ID
Output: None
"""
def process_report(report_ID):
   ## Gets lead ID for given Checkr report ID in DynamoDB table
   checkr_report_ID = report_ID
   dynamodb = boto3.resource('dynamodb')
   background_check_table = dynamodb.Table(settings.backgroundCheckTable)
   report_ID_query = background_check_table.scan(FilterExpression=Attr('checkr_report_ID').eq(checkr_report_ID))
   salesforce_lead_name = report_ID_query['Items'][0]['name']
   salesforce_lead_ID = report_ID_query['Items'][0]['salesforce_lead_ID']
   
   ## Updates DynamoDB table to indicate that Checkr report is completed
   print("Updating status to 'report_completed' in DynamoDB table for Checkr report (report_ID: " + checkr_report_ID + ")")
   response = background_check_table.update_item(
    Key={'salesforce_lead_ID': salesforce_lead_ID},
    UpdateExpression="set checkr_status=:v1",
    ExpressionAttributeValues={
        ':v1': "report completed",
    },
    ReturnValues="UPDATED_NEW"
   )

   ### Retrieves Checkr report with corresponding report_ID through GET request to Checkr API
   print("")
   print("Retrieving completed report from Checkr (report_ID: " + checkr_report_ID + ")")
   params = {'include':['ssn_trace,sex_offender_search,global_watchlist_search,national_criminal_search']}
   retrieve_report_response = requests.get(url = settings.checkrBaseUrl + '/v1/reports/' + checkr_report_ID, auth = (settings.checkrApiKey, ''), params = params)
   report_results_object = retrieve_report_response.json()
   retrieve_report_response.close()
   ## If error in retrieving Checkr report, creates a Salesforce 'Background Check' object with error for given lead, and returns error code
   ## Also returns error code which terminates background check process
   if retrieve_report_response.ok == False:
      error_retrieve_report = report_results_object['error'][0]
      print("error_retrieve_report: " + error_retrieve_report)
      ### Creates 'Background Check' object payload for given Salesforce lead and updates it with error and incomplete 'background_check' status
      BC_object_error_payload = get_BC_object_payload(salesforce_lead_ID, salesforce_lead_name)
      BC_object_error_payload['Error_Retrieve_Report__c'] = error_retrieve_report
      BC_object_error_payload['Status_Background_Check__c'] = 'incomplete'
      ### Creates a Salesforce 'Background Check' object with error for given lead
      call = sf_api_call("/services/data/v49.0/sobjects/Background_Check__c", method = "post", data = BC_object_error_payload)
      BC_object_id = call.get('id')
      print("Created Background Check object (" + BC_object_id + ") for Salesforce lead containing error")  
      ## Returns error 
      return Response(status = 400)
   else:
      print("No errors in retrieving report")
   
   ## If error in SSN Trace, Sex Offender Search, Global Watchlist Search, or National Criminal Search, creates a Salesforce 'Background Check' object with error for given lead
   ## Also returns error code
   ssn_trace_object = report_results_object['ssn_trace']
   print(ssn_trace_object)
   sex_offender_search_object = report_results_object['sex_offender_search']
   print(sex_offender_search_object)
   global_watchlist_search_object = report_results_object['global_watchlist_search']
   print(global_watchlist_search_object)
   national_criminal_search_object = report_results_object['national_criminal_search']
   print(national_criminal_search_object)
   background_check_objects = [ssn_trace_object, sex_offender_search_object, global_watchlist_search_object, national_criminal_search_object]
   for object in background_check_objects:
      if "error" in object:
         ### Creates 'Background Check' object payload for given Salesforce lead and updates it with error and incomplete 'background_check' status         
         BC_object_error_payload = get_BC_object_payload(salesforce_lead_ID, salesforce_lead_name)
         screening_name_original = object["object"]
         if "test" in screening_name_original:
            screening_name_edited = screening_name_original.replace("test_", "", 1)
            error_field_name = 'Error_' + screening_name_edited + '__c'
         else:
            error_field_name = 'Error_' + screening_name_original + '__c'
         BC_object_error_payload[error_field_name] = object['error'][0]
         BC_object_error_payload['Status_Background_Check__c'] = 'incomplete'
         ### Creates a Salesforce 'Background Check' object with error for given lead         
         call = sf_api_call("/services/data/v49.0/sobjects/Background_Check__c", method = "post", data = BC_object_error_payload)
         BC_object_id = call.get('id')
         print("Error in " + object["object"] + ": " + object['error'][0])
         print("Created Background Check object (" + BC_object_id + ") for Salesforce lead containing error")   
         return Response(status = 400)
   print("")
   print("No errors in SSN Trace, Sex Offender Search, Global Watchlist Search, and National Criminal Search")
      
   ## Parses Checkr report, creates 'Background Check' object payload for given Salesforce lead, and updates 'Background Check' object payload with report contents 
   print("Results of Checkr report (report_ID: " + checkr_report_ID + ")")
   BC_object_payload = get_BC_object_payload(salesforce_lead_ID, salesforce_lead_name)
   BC_object_payload['Status_Background_Check__c'] = report_results_object['status'] 
   print("")
   print("overall status: " + report_results_object['status'])
   BC_object_payload['Turnaround_Time_Background_Check__c'] = report_results_object['turnaround_time']
   ssn_trace_object = report_results_object['ssn_trace']
   BC_object_payload['SSN_Trace_Status__c'] = ssn_trace_object['status']   
   print("ssn_trace_status: " + ssn_trace_object['status'])
   BC_object_payload['Turnaround_Time_SSN_Trace__c'] = ssn_trace_object['turnaround_time']
   BC_object_payload['No_Data__c'] = ssn_trace_object['no_data']
   BC_object_payload['DOB_Mismatch__c'] = ssn_trace_object['dob_mismatch']
   BC_object_payload['Name_Mismatch__c'] = ssn_trace_object['name_mismatch']
   BC_object_payload['Data_Mismatch__c'] = ssn_trace_object['data_mismatch']
   BC_object_payload['Thin_File__c'] = ssn_trace_object['thin_file']
   BC_object_payload['Invalid_Issuance_Year__c'] = ssn_trace_object['invalid_issuance_year']
   BC_object_payload['Death_Index__c'] = ssn_trace_object['death_index']
   BC_object_payload['SSN_Already_Taken__c'] = ssn_trace_object['ssn_already_taken']
   BC_object_payload['Issued_Year__c'] = ssn_trace_object['issued_year']
   BC_object_payload['Issued_State__c'] = ssn_trace_object['issued_state']
   BC_object_payload['Addresses__c'] = str(ssn_trace_object['addresses'])
   BC_object_payload['Aliases__c'] = str(ssn_trace_object['aliases'])
   BC_object_payload['Sex_Offender_Registry_Search_Status__c'] = report_results_object['sex_offender_search']['status']
   print("sex_offender_registry_search_status: " + report_results_object['sex_offender_search']['status'])
   BC_object_payload['Turnaround_Time_Sex_Offender_Search__c'] =  report_results_object['sex_offender_search']['turnaround_time']
   BC_object_payload['Sex_Offender_Records__c'] =  str(report_results_object['sex_offender_search']['records'])
   BC_object_payload['Global_Watchlist_Status__c'] = report_results_object['global_watchlist_search']['status']
   print("global_watchlist_status: " + report_results_object['global_watchlist_search']['status'])
   BC_object_payload['Turnaround_Time_Global_Watchlist__c'] = report_results_object['global_watchlist_search']['turnaround_time']
   BC_object_payload['Global_Watchlist_Records__c'] = str(report_results_object['global_watchlist_search']['records'])
   BC_object_payload['National_Criminal_Search_Status__c'] = report_results_object['national_criminal_search']['status']
   print("national_criminal_search_status: " + report_results_object['national_criminal_search']['status'])   
   BC_object_payload['Turnaround_Time_National_Criminal_Search__c'] = report_results_object['national_criminal_search']['turnaround_time']
   BC_object_payload['National_Criminal_Search_Records__c'] = str(report_results_object['national_criminal_search']['records'])
   
   ### Creates 'Background Check' object for given Salesforce lead
   print("")
   print("Updating Salesforce lead (lead_ID: " + salesforce_lead_ID + ") with background check results")   
   call = sf_api_call("/services/data/v49.0/sobjects/Background_Check__c", method = "post", data = BC_object_payload)
   BC_object_id = call.get('id')
   print('Background Check object ID: ' + BC_object_id)
   print("")

'''
Creates and returns 'Background Check' object payload for given Salesforce lead
Input: Salesforce lead ID and lead name
Output: 'Background Check' object payload for given Salesforce lead
'''
def get_BC_object_payload(salesforce_lead_ID, salesforce_lead_name):
   BC_object_payload = {'Name': salesforce_lead_name, 'Lead__c': salesforce_lead_ID, 'Request_Background_Check__c': True, 'Status_Background_Check__c': '', 
                        'Turnaround_Time_Background_Check__c': '', 'Error_ssn_trace__c':'', 'SSN_Trace_Status__c': '', 'Turnaround_Time_SSN_Trace__c': '', 
                        'No_Data__c': '', 'DOB_Mismatch__c': '', 'Name_Mismatch__c': '', 'Data_Mismatch__c': '', 'Thin_File__c': '', 'Invalid_Issuance_Year__c': '', 
                        'Death_Index__c': '', 'SSN_Already_Taken__c': '', 'Issued_Year__c': '', 'Issued_State__c': '', 'Addresses__c': '', 'Aliases__c': '', 
                        'Error_sex_offender_search__c':'', 'Sex_Offender_Registry_Search_Status__c': '', 'Turnaround_Time_Sex_Offender_Search__c': '', 'Sex_Offender_Records__c': '',
                        'Error_global_watchlist_search__c':'', 'Global_Watchlist_Status__c': '', 'Turnaround_Time_Global_Watchlist__c': '', 'Global_Watchlist_Records__c': '',
                        'Error_national_criminal_search__c':'', 'National_Criminal_Search_Status__c': '', 'Turnaround_Time_National_Criminal_Search__c': '',
                        'National_Criminal_Search_Records__c': '', 'Error_Create_Candidate__c': '', 'Error_Create_Report__c': '', 'Error_Retrieve_Report__c': ''}

   return BC_object_payload


'''
Helper function to make calls to Salesforce REST API 
Parameters: action (the Salesforce URL), Salesforce URL params, method (get, post or patch), data for POST/PATCH
Output: None
'''
def sf_api_call(action, parameters = {}, method = 'get', data = {}):
   ## Obtains access token and instance URL using Connected App and OAuth 2.0 authorization flow
   ## Need access token and instance URL to make calls to Salesforce
   params = {"grant_type": "password", "client_id": settings.salesforceClientID, "client_secret": settings.salesforceClientSecret,
             "username": settings.salesforceUsername, "password": settings.salesforcePassword}
   sf_response = requests.post(settings.salesforceOAuthURL, params=params)
   sf_response_json = sf_response.json()
   if "error" in sf_response_json:
      print(sf_response_json.get("error"))
      print(sf_response_json.get("error_description"))
   else:
      access_token = sf_response_json.get("access_token")
      instance_url = sf_response_json.get("instance_url")
      print("")
      print("Obtaining Salesforce access token and instance URL using Connected App and Oauth authorization flow")

   headers = {'Content-type': 'application/json', 'Accept-Encoding': 'gzip', 'Authorization': 'Bearer %s' % access_token}

   if method == 'get':
      r = requests.request(method, instance_url+action, headers = headers, params = parameters, timeout = 30)
   elif method in ['post', 'patch']:
      r = requests.request(method, instance_url+action, headers = headers, json = data, params = parameters, timeout = 30)
   else:
      raise ValueError('Method should be post or patch')
   if r.status_code < 300:
      if method == 'patch':
         return None
      else:
         return r.json()
   else:
      raise Exception('API Error when calling %s: %s' % (r.url, r.content))

'''
Builds and returns XML acknowledgement to Salesforce outbound message
Input: None
Output: XML acknowledgement to Salesforce outbound message
'''
def get_sf_outbound_msg_acknowledgement():
   ## Builds XML acknowledgement for Salesforce outbound message using Element Tree
   root = ET.Element("soapenv:Envelope")
   root.set("xmlns:soapenv", "http://schemas.xmlsoap.org/soap/envelope/")
   root.set("xmlns:xsd", "http://www.w3.org/2001/XMLSchema")
   root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
   body = ET.SubElement(root, 'soapenv:Body')
   notificationsResponse = ET.SubElement(body, 'notificationsResponse')
   notificationsResponse.set('xmlns',"http://soap.sforce.com/2005/09/outbound")
   Ack = ET.SubElement(notificationsResponse, 'Ack')
   Ack.text='true'
   return Response(ET.tostring(root), mimetype='application/xml')   
   



"""
Receives webhooks from Checkr API at separate endpoint to check whether report has been completed
Once endpoint recieves 'report_completed' webhook, retrieves report ID of completed Checkr report and processes it with process_report()
"""
@app.route('/checkr', methods=['POST'])
def check_report_status():
   print("")
   print("Receiving Checkr webhooks and checking whether report completed")
   print(request.json)
   webhook_object = request.json
   if "report.completed" == webhook_object["type"]:
      ## Retrieves report ID of completed Checkr report
      checkr_report_ID = webhook_object["data"]["object"]["id"]
      print("")
      print("Report (report_ID: " + checkr_report_ID + ") has been completed")
      dynamodb = boto3.resource('dynamodb')
      background_check_table = dynamodb.Table(settings.backgroundCheckTable)
      report_ID_query = background_check_table.scan(FilterExpression=Attr('checkr_report_ID').eq(checkr_report_ID))
      if report_ID_query['Count'] != 0 and report_ID_query['Items'][0]['checkr_status'] != "report_completed":
         process_report(checkr_report_ID)
      else:
         print("Report (report_ID: " + checkr_report_ID + ") already completed so not processing again!")

   return Response(status = 200)
