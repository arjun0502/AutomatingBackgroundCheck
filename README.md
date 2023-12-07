# Automating Background Check
Automation of background check process for the Believe in Me Foundation using a technology stack including Python, Linux, Salesforce, AWS Lambda, and DynamoDB. Created Flask application in Python to communicate with Salesforce and “Checkr” background check REST APIs.

### How to run the background check process

Every Salesforce volunteer lead has a 'Request Background Check' trigger. When this trigger changes in value from 'False' to 'True', the background check process will be started for the corresponding Salesforce lead. You can change the value from ‘False’ to ‘True’ by checking the 'Request Background Check' trigger and then saving the Salesforce Lead. If it is already checked and you need to run again, unclick the trigger, save the Salesforce lead, recheck the trigger, and then save the Salesforce lead again. 

### Endpoints

The background check process has two endpoints: ‘/background-check’ and ‘/checkr’. The ‘/checkr’ endpoint receives webhook updates from Checkr API to check whether a report is completed, while the rest of the background check process is handled by the ‘/background-check’ endpoint. For both the Live and Test Checkr API, the ‘/checkr’ endpoint is configured in the Checkr Dashboard under ‘Developer Settings’ found in the ‘Account Settings’ tab. The ‘/background-check’ endpoint is configured in the ‘Outbound Message’ Setup section of both Production and Sandbox Salesforce. 

### Production vs. QA

Everything is set up in ‘settings.py’ so that the AWS Production environment (including DynamoDB table) corresponds with Checkr’s ‘Live’ environment while the AWS QA environment (including DynamoDB table) corresponds with Checkr’s ‘Test’ environment. You do not need to change anything to do testing and perform QA except run the background check process from Sandbox Salesforce. 

### Monitoring 

#### CloudWatch Logs in AWS

If you have access to AWS, you can monitor the background check process in the CloudWatch Logs in AWS (available for both QA and Prod environments). You do need special permission to access AWS and the CloudWatch Logs. The script prints out each step of the process and so it is very clear to follow. 

#### AWS DynamoDB table

The script uses the AWS DynamoDB table to keep track of all the background checks run. There is a table for both the AWS QA and Prod environment. Every item in the table corresponds to a Salesforce lead and contains the lead ID and name, Checkr candidate ID, Checkr report ID, and Checkr status 
The ‘checkr_status’ attribute has three values (candidate created, report created, report completed) and you can look at this attribute to monitor the background check process for Salesforce leads. Like the CloudWatch logs, you need special permission to access AWS. 

#### Checkr dashboard

The Checkr dashboard can also be used to monitor the background check process. It has a tab for both the ‘Live’ and ‘Test’ Checkr environments which corresponds to AWS Production and QA environments respectively. Within each tab, there is a tab called ‘Candidates’ where you can monitor the background check process for each candidate. There is also a tab called ‘Logs’ where you can monitor each POST/GET request made to the Checkr API by the script. You can get the login details for the Checkr dashboard on LastPass or ask Julie. 

### Background Check Results

Once the background check report is completed for a Salesforce lead, a Salesforce ‘Background Check’ object is created for the lead. This ‘Background Check’ object contains all the results of the background check. 

#### In case of error

If there is an error in the background check process, a Salesforce ‘Background Check’ object will be created for the lead and it will contain the error. For example, if there is something wrong with a lead’s SSN, the background check process will be terminated and a ‘Background Check’ object will be created for the lead with the ‘Error_Create_Candidate’ field as ‘SSN is invalid’. 

### Acknowledgement of Salesforce Outbound Message

After an outbound message is sent from Salesforce, it needs to be acknowledged or it will keep sending the outbound message. The outbound message is acknowledged by returning a XML containing ‘Ack = true’. The script acknowledges the outbound message after an error occurs or at the end of successfully creating a report. 
