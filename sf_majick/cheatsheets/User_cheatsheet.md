# User Fields Cheatsheet

| Field Name | Label | Type |
|------------|-------|------|
| Id | User ID | id |
| Username | Username | string |
| LastName | Last Name | string |
| FirstName | First Name | string |
| Name | Full Name | string |
| CompanyName | Company Name | string |
| Division | Division | string |
| Department | Department | string |
| Title | Title | string |
| Street | Street | textarea |
| City | City | string |
| State | State/Province | string |
| PostalCode | Zip/Postal Code | string |
| Country | Country | string |
| Latitude | Latitude | double |
| Longitude | Longitude | double |
| GeocodeAccuracy | Geocode Accuracy | picklist |
| Address | Address | address |
| Email | Email | email |
| EmailPreferencesAutoBcc | AutoBcc | boolean |
| EmailPreferencesAutoBccStayInTouch | AutoBccStayInTouch | boolean |
| EmailPreferencesStayInTouchReminder | StayInTouchReminder | boolean |
| SenderEmail | Email Sender Address | email |
| SenderName | Email Sender Name | string |
| Signature | Email Signature | textarea |
| StayInTouchSubject | Stay-in-Touch Email Subject | string |
| StayInTouchSignature | Stay-in-Touch Email Signature | textarea |
| StayInTouchNote | Stay-in-Touch Email Note | string |
| Phone | Phone | phone |
| Fax | Fax | phone |
| MobilePhone | Mobile | phone |
| Alias | Alias | string |
| CommunityNickname | Nickname | string |
| BadgeText | User Photo badge text overlay | string |
| IsActive | Active | boolean |
| TimeZoneSidKey | Time Zone | picklist |
| UserRoleId | Role ID | reference |
| LocaleSidKey | Locale | picklist |
| ReceivesInfoEmails | Info Emails | boolean |
| ReceivesAdminInfoEmails | Admin Info Emails | boolean |
| EmailEncodingKey | Email Encoding | picklist |
| ProfileId | Profile ID | reference |
| UserType | User Type | picklist |
| StartDay | Start of Day | picklist |
| EndDay | End of Day | picklist |
| LanguageLocaleKey | Language | picklist |
| EmployeeNumber | Employee Number | string |
| DelegatedApproverId | Delegated Approver ID | reference |
| ManagerId | Manager ID | reference |
| LastLoginDate | Last Login | datetime |
| LastPasswordChangeDate | Last Password Change or Reset | datetime |
| CreatedDate | Created Date | datetime |
| CreatedById | Created By ID | reference |
| LastModifiedDate | Last Modified Date | datetime |
| LastModifiedById | Last Modified By ID | reference |
| SystemModstamp | System Modstamp | datetime |
| PasswordExpirationDate | Password Expiration Date | datetime |
| NumberOfFailedLogins | Failed Login Attempts | int |
| SuAccessExpirationDate | SU Access Expiration Date | date |
| OfflineTrialExpirationDate | Offline Edition Trial Expiration Date | datetime |
| OfflinePdaTrialExpirationDate | Sales Anywhere Trial Expiration Date | datetime |
| UserPermissionsMarketingUser | Marketing User | boolean |
| UserPermissionsOfflineUser | Offline User | boolean |
| UserPermissionsCallCenterAutoLogin | Auto-login To Call Center | boolean |
| UserPermissionsSFContentUser | Salesforce CRM Content User | boolean |
| UserPermissionsKnowledgeUser | Knowledge User | boolean |
| UserPermissionsInteractionUser | Flow User | boolean |
| UserPermissionsSupportUser | Service Cloud User | boolean |
| UserPermissionsJigsawProspectingUser | Data.com User | boolean |
| UserPermissionsSiteforceContributorUser | Site.com Contributor User | boolean |
| UserPermissionsSiteforcePublisherUser | Site.com Publisher User | boolean |
| UserPermissionsWorkDotComUserFeature | WDC User | boolean |
| ForecastEnabled | Allow Forecasting | boolean |
| UserPreferencesActivityRemindersPopup | ActivityRemindersPopup | boolean |
| UserPreferencesEventRemindersCheckboxDefault | EventRemindersCheckboxDefault | boolean |
| UserPreferencesTaskRemindersCheckboxDefault | TaskRemindersCheckboxDefault | boolean |
| UserPreferencesReminderSoundOff | ReminderSoundOff | boolean |
| UserPreferencesDisableAllFeedsEmail | DisableAllFeedsEmail | boolean |
| UserPreferencesDisableFollowersEmail | DisableFollowersEmail | boolean |
| UserPreferencesDisableProfilePostEmail | DisableProfilePostEmail | boolean |
| UserPreferencesDisableChangeCommentEmail | DisableChangeCommentEmail | boolean |
| UserPreferencesDisableLaterCommentEmail | DisableLaterCommentEmail | boolean |
| UserPreferencesDisProfPostCommentEmail | DisProfPostCommentEmail | boolean |
| UserPreferencesContentNoEmail | ContentNoEmail | boolean |
| UserPreferencesContentEmailAsAndWhen | ContentEmailAsAndWhen | boolean |
| UserPreferencesApexPagesDeveloperMode | ApexPagesDeveloperMode | boolean |
| UserPreferencesReceiveNoNotificationsAsApprover | ReceiveNoNotificationsAsApprover | boolean |
| UserPreferencesReceiveNotificationsAsDelegatedApprover | ReceiveNotificationsAsDelegatedApprover | boolean |
| UserPreferencesHideCSNGetChatterMobileTask | HideCSNGetChatterMobileTask | boolean |
| UserPreferencesDisableMentionsPostEmail | DisableMentionsPostEmail | boolean |
| UserPreferencesDisMentionsCommentEmail | DisMentionsCommentEmail | boolean |
| UserPreferencesHideCSNDesktopTask | HideCSNDesktopTask | boolean |
| UserPreferencesHideChatterOnboardingSplash | HideChatterOnboardingSplash | boolean |
| UserPreferencesHideSecondChatterOnboardingSplash | HideSecondChatterOnboardingSplash | boolean |
| UserPreferencesDisCommentAfterLikeEmail | DisCommentAfterLikeEmail | boolean |
| UserPreferencesDisableLikeEmail | DisableLikeEmail | boolean |
| UserPreferencesSortFeedByComment | SortFeedByComment | boolean |
| UserPreferencesDisableMessageEmail | DisableMessageEmail | boolean |
| UserPreferencesJigsawListUser | JigsawListUser | boolean |
| UserPreferencesDisableBookmarkEmail | DisableBookmarkEmail | boolean |
| UserPreferencesDisableSharePostEmail | DisableSharePostEmail | boolean |
| UserPreferencesEnableAutoSubForFeeds | EnableAutoSubForFeeds | boolean |
| UserPreferencesDisableFileShareNotificationsForApi | DisableFileShareNotificationsForApi | boolean |
| UserPreferencesShowTitleToExternalUsers | ShowTitleToExternalUsers | boolean |
| UserPreferencesShowManagerToExternalUsers | ShowManagerToExternalUsers | boolean |
| UserPreferencesShowEmailToExternalUsers | ShowEmailToExternalUsers | boolean |
| UserPreferencesShowWorkPhoneToExternalUsers | ShowWorkPhoneToExternalUsers | boolean |
| UserPreferencesShowMobilePhoneToExternalUsers | ShowMobilePhoneToExternalUsers | boolean |
| UserPreferencesShowFaxToExternalUsers | ShowFaxToExternalUsers | boolean |
| UserPreferencesShowStreetAddressToExternalUsers | ShowStreetAddressToExternalUsers | boolean |
| UserPreferencesShowCityToExternalUsers | ShowCityToExternalUsers | boolean |
| UserPreferencesShowStateToExternalUsers | ShowStateToExternalUsers | boolean |
| UserPreferencesShowPostalCodeToExternalUsers | ShowPostalCodeToExternalUsers | boolean |
| UserPreferencesShowCountryToExternalUsers | ShowCountryToExternalUsers | boolean |
| UserPreferencesShowProfilePicToGuestUsers | ShowProfilePicToGuestUsers | boolean |
| UserPreferencesShowTitleToGuestUsers | ShowTitleToGuestUsers | boolean |
| UserPreferencesShowCityToGuestUsers | ShowCityToGuestUsers | boolean |
| UserPreferencesShowStateToGuestUsers | ShowStateToGuestUsers | boolean |
| UserPreferencesShowPostalCodeToGuestUsers | ShowPostalCodeToGuestUsers | boolean |
| UserPreferencesShowCountryToGuestUsers | ShowCountryToGuestUsers | boolean |
| UserPreferencesShowForecastingChangeSignals | ShowForecastingChangeSignals | boolean |
| UserPreferencesLiveAgentMiawSetupDeflection | LiveAgentMiawSetupDeflection | boolean |
| UserPreferencesHideS1BrowserUI | HideS1BrowserUI | boolean |
| UserPreferencesDisableEndorsementEmail | DisableEndorsementEmail | boolean |
| UserPreferencesPathAssistantCollapsed | PathAssistantCollapsed | boolean |
| UserPreferencesCacheDiagnostics | CacheDiagnostics | boolean |
| UserPreferencesShowEmailToGuestUsers | ShowEmailToGuestUsers | boolean |
| UserPreferencesShowManagerToGuestUsers | ShowManagerToGuestUsers | boolean |
| UserPreferencesShowWorkPhoneToGuestUsers | ShowWorkPhoneToGuestUsers | boolean |
| UserPreferencesShowMobilePhoneToGuestUsers | ShowMobilePhoneToGuestUsers | boolean |
| UserPreferencesShowFaxToGuestUsers | ShowFaxToGuestUsers | boolean |
| UserPreferencesShowStreetAddressToGuestUsers | ShowStreetAddressToGuestUsers | boolean |
| UserPreferencesLightningExperiencePreferred | LightningExperiencePreferred | boolean |
| UserPreferencesPreviewLightning | PreviewLightning | boolean |
| UserPreferencesHideEndUserOnboardingAssistantModal | HideEndUserOnboardingAssistantModal | boolean |
| UserPreferencesHideLightningMigrationModal | HideLightningMigrationModal | boolean |
| UserPreferencesHideSfxWelcomeMat | HideSfxWelcomeMat | boolean |
| UserPreferencesHideBiggerPhotoCallout | HideBiggerPhotoCallout | boolean |
| UserPreferencesGlobalNavBarWTShown | GlobalNavBarWTShown | boolean |
| UserPreferencesGlobalNavGridMenuWTShown | GlobalNavGridMenuWTShown | boolean |
| UserPreferencesCreateLEXAppsWTShown | CreateLEXAppsWTShown | boolean |
| UserPreferencesFavoritesWTShown | FavoritesWTShown | boolean |
| UserPreferencesRecordHomeSectionCollapseWTShown | RecordHomeSectionCollapseWTShown | boolean |
| UserPreferencesRecordHomeReservedWTShown | RecordHomeReservedWTShown | boolean |
| UserPreferencesFavoritesShowTopFavorites | FavoritesShowTopFavorites | boolean |
| UserPreferencesExcludeMailAppAttachments | ExcludeMailAppAttachments | boolean |
| UserPreferencesSuppressTaskSFXReminders | SuppressTaskSFXReminders | boolean |
| UserPreferencesSuppressEventSFXReminders | SuppressEventSFXReminders | boolean |
| UserPreferencesPreviewCustomTheme | PreviewCustomTheme | boolean |
| UserPreferencesHasCelebrationBadge | HasCelebrationBadge | boolean |
| UserPreferencesUserDebugModePref | UserDebugModePref | boolean |
| UserPreferencesSRHOverrideActivities | SRHOverrideActivities | boolean |
| UserPreferencesNewLightningReportRunPageEnabled | NewLightningReportRunPageEnabled | boolean |
| UserPreferencesReverseOpenActivitiesView | ReverseOpenActivitiesView | boolean |
| UserPreferencesHasSentWarningEmail | HasSentWarningEmail | boolean |
| UserPreferencesHasSentWarningEmail238 | HasSentWarningEmail238 | boolean |
| UserPreferencesHasSentWarningEmail240 | HasSentWarningEmail240 | boolean |
| UserPreferencesNativeEmailClient | NativeEmailClient | boolean |
| UserPreferencesShowForecastingRoundedAmounts | ShowForecastingRoundedAmounts | boolean |
| ContactId | Contact ID | reference |
| AccountId | Account ID | reference |
| CallCenterId | Call Center ID | reference |
| Extension | Extension | phone |
| FederationIdentifier | SAML Federation ID | string |
| AboutMe | About Me | textarea |
| FullPhotoUrl | Url for full-sized Photo | url |
| SmallPhotoUrl | Photo | url |
| IsExtIndicatorVisible | Show external indicator | boolean |
| OutOfOfficeMessage | Out of office message | string |
| MediumPhotoUrl | Url for medium profile photo | url |
| DigestFrequency | Chatter Email Highlights Frequency | picklist |
| DefaultGroupNotificationFrequency | Default Notification Frequency when Joining Groups | picklist |
| JigsawImportLimitOverride | Data.com Monthly Addition Limit | int |
| LastViewedDate | Last Viewed Date | datetime |
| LastReferencedDate | Last Referenced Date | datetime |
| BannerPhotoUrl | Url for banner photo | url |
| SmallBannerPhotoUrl | Url for IOS banner photo | url |
| MediumBannerPhotoUrl | Url for Android banner photo | url |
| IsProfilePhotoActive | Has Profile Photo | boolean |
| IndividualId | Individual ID | reference |
