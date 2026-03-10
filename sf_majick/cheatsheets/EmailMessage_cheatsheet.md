# EmailMessage Fields Cheatsheet

| Field Name | Label | Type |
|------------|-------|------|
| Id | Email Message ID | id |
| ParentId | Case ID | reference |
| ActivityId | Activity ID | reference |
| CreatedById | Created By ID | reference |
| CreatedDate | Created Date | datetime |
| LastModifiedDate | Last Modified Date | datetime |
| LastModifiedById | Last Modified By ID | reference |
| SystemModstamp | System Modstamp | datetime |
| TextBody | Text Body | textarea |
| HtmlBody | HTML Body | textarea |
| Headers | Headers | textarea |
| Subject | Subject | string |
| Name | Email Message Name | string |
| FromName | From Name | string |
| FromAddress | From Address | email |
| ValidatedFromAddress | From | picklist |
| ToAddress | To Address | string |
| CcAddress | CC Address | string |
| BccAddress | BCC Address | string |
| Incoming | Is Incoming | boolean |
| HasAttachment | Has Attachment | boolean |
| Status | Status | picklist |
| MessageDate | Message Date | datetime |
| IsDeleted | Deleted | boolean |
| ReplyToEmailMessageId | Email Message ID | reference |
| IsExternallyVisible | Is Externally Visible | boolean |
| MessageIdentifier | Message ID | string |
| ThreadIdentifier | Thread ID | string |
| ClientThreadIdentifier | Client Thread ID | string |
| IsClientManaged | Is Client Managed | boolean |
| RelatedToId | Related To ID | reference |
| IsTracked | Is Tracked | boolean |
| IsOpened | Opened? | boolean |
| FirstOpenedDate | First Opened | datetime |
| LastOpenedDate | Last Opened | datetime |
| IsBounced | Bounced? | boolean |
| EmailTemplateId | Email Template ID | reference |
