# Salesforce SOQL Cheatsheet

## Basic Queries
SELECT field1, field2 FROM ObjectName
SELECT Name, Industry FROM Account

## Filtering
WHERE field = 'Value'
WHERE Amount > 1000
WHERE CreatedDate >= 2024-01-01T00:00:00Z

## Sorting
ORDER BY field ASC|DESC
ORDER BY CreatedDate DESC

## Limiting
LIMIT 10
LIMIT 100

## Aggregations
SELECT COUNT(Id) FROM Opportunity
SELECT MAX(Amount), MIN(Amount) FROM Opportunity

## Functions
FORMAT(), CALENDAR_YEAR(), CALENDAR_MONTH(), DAY_IN_MONTH(), etc.

## Relationships
- Parent-to-child: SELECT Name, (SELECT LastName FROM Contacts) FROM Account
- Child-to-parent: SELECT Contact.Account.Name FROM Contact

## Operators
=, !=, <, <=, >, >=, LIKE, IN, NOT IN, INCLUDES, EXCLUDES, NULL, NOT NULL

## Combining Filters
AND, OR
