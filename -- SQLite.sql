-- SQLite

-- All Tables
SELECT name FROM sqlite_master WHERE type='table';

-- Columsn per Table
PRAGMA table_info(engagements);


SELECT id, smsContent, smsTiming, send_datetime_utc, status 
FROM roadmap_messages 
WHERE customer_id = 2;

SELECT * FROM roadmap_messages WHERE customer_id = 1;


SELECT * FROM roadmap_messages WHERE customer_id = 1;


SELECT id, smsContent, smsTiming, send_datetime_utc, status 
FROM roadmap_messages 
WHERE customer_id = 1;

SELECT * FROM roadmap_messages WHERE customer_id = 2;


SELECT id, business_name FROM business_profiles;


SELECT * FROM business_profiles;

SELECT id, smsContent, smsTiming, send_datetime_utc, status 
FROM roadmap_messages 
WHERE customer_id = 1;

SELECT id, customer_name, business_id FROM customers;

SELECT COUNT(*) FROM roadmap_messages WHERE customer_id = 1;

SELECT COUNT(*) FROM scheduled_sms WHERE customer_id = 1;


SELECT * FROM roadmap_messages WHERE id = 1;

SELECT * FROM scheduled_sms WHERE id = 1;


SELECT
  r.id AS roadmap_id,
  s.id AS scheduled_id,
  r.customer_id,
  r.smsContent,
  s.message,
  r.send_datetime_utc,
  s.send_time
FROM roadmap_messages r
JOIN scheduled_sms s
  ON r.customer_id = s.customer_id
 AND r.business_id = s.business_id
 AND r.smsContent = s.message
 AND r.send_datetime_utc = s.send_time;



SELECT customer_id, COUNT(*) as roadmap_count
FROM roadmap_messages
WHERE status = 'approved'
GROUP BY customer_id;

SELECT customer_id, COUNT(*) as scheduled_count
FROM scheduled_sms
GROUP BY customer_id;


SELECT rm.id, ss.id
FROM roadmap_messages rm
JOIN scheduled_sms ss ON
  rm.customer_id = ss.customer_id AND
  rm.smsContent = ss.message AND
  rm.send_datetime_utc = ss.send_time
WHERE rm.status = 'scheduled';


SELECT id, message, status, send_time
FROM scheduled_sms
WHERE status = 'sent'
ORDER BY send_time DESC;

SELECT id, customer_id, message, send_time FROM scheduled_sms WHERE status = 'scheduled';

SELECT id, phone FROM customers WHERE id = [customer_id];


SELECT id, message, send_time FROM scheduled_sms WHERE status = 'scheduled';



SELECT id, message, status, send_time
FROM scheduled_sms
WHERE send_time <= DATETIME('now')
AND status = 'scheduled'
ORDER BY send_time DESC;

SELECT * from scheduled_sms

SELECT id, customer_id, message, send_time
FROM scheduled_sms
ORDER BY id;


SELECT id, message, status, send_time
FROM scheduled_sms
WHERE id = 2;


SELECT id, message, send_time FROM scheduled_sms ORDER BY id;

SELECT id, customer_id, message, status, send_time FROM scheduled_sms ORDER BY id;


SELECT id, customer_id, message, status, send_time
FROM scheduled_sms
WHERE id = 2;


SELECT * FROM roadmap_messages WHERE id = 2;

SELECT id, message FROM scheduled_sms;

SELECT * FROM scheduled_sms WHERE id = 2;


SELECT send_datetime_utc FROM roadmap_messages;

SELECT send_time FROM scheduled_sms


Select * FROM scheduled_sms;

Select * FROM roadmap_messages;

SELECT * FROM scheduled_sms WHERE id = 1;
SELECT * FROM scheduled_sms WHERE id = 1;


SELECT id, customer_id, business_id, message, send_time
FROM scheduled_sms
WHERE id = 3;

SELECT id, message, send_time FROM scheduled_sms ORDER BY id DESC;

select * from customers;


SELECT * FROM engagements ORDER BY id DESC;

ALTER TABLE engagements ADD COLUMN ai_response TEXT;

ALTER TABLE engagements ADD COLUMN status TEXT DEFAULT 'pending_review';




SELECT id, customer_id, message, send_time, status
FROM scheduled_sms
ORDER BY send_time;

SELECT * FROM scheduled_sms
WHERE message LIKE '%Hope you\'re well. Just a quick check-in%';


ALTER TABLE engagements ADD COLUMN sent_at DATETIME;

ALTER TABLE business_profiles ADD COLUMN twilio_number VARCHAR;

SeLECT * FROM business_profiles;


sqlite3 database.db
SELECT * FROM customers WHERE phone = '+13856268825';

SELECT * FROM business_profiles;
SELECT * FROM customers;

ALTER TABLE business_profiles ADD COLUMN slug VARCHAR UNIQUE;