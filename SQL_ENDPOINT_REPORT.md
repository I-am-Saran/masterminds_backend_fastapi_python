# SQL Endpoint Report

This report is generated from static code analysis (FastAPI route decorators + SQL call sites).
TableProxy calls are converted into SQL templates based on services/db_service.py.

## GET /actions
- Handler: main.py:252-293
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /actions
- Handler: main.py:341-381
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /actions/{action_id}
- Handler: main.py:435-472
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /actions/{action_id}
- Handler: main.py:298-336
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /actions/{action_id}
- Handler: main.py:386-430
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api
- Handler: app/admin/projects_router.py:164-205
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api
- Handler: app/legacy/certifications.py:13-48
- SQL (execute_query) app/legacy/certifications.py:40-40
  - Tables: (unknown)
  - Query: `{...}`

## GET /api
- Handler: app/meetings/mrm_router.py:56-76
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api
- Handler: app/tenants/router.py:20-39
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api
- Handler: app/admin/projects_router.py:295-374
- SQL (execute_query) app/admin/projects_router.py:323-327
  - Tables: projects
  - Query: `SELECT id FROM projects WHERE application_name = %s AND ((tenant_id = %s) OR (tenant_id IS NULL AND %s IS NULL))`

## POST /api
- Handler: app/meetings/mrm_router.py:80-98
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/
- Handler: app/legacy/incident_register.py:65-84
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/
- Handler: app/legacy/risk_register.py:59-78
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/
- Handler: app/admin/testcase_router.py:16-23
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/
- Handler: app/legacy/incident_register.py:88-104
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/
- Handler: app/legacy/risk_register.py:108-134
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/action-items
- Handler: app/meetings/router.py:631-754
- SQL (execute_query) app/meetings/router.py:720-724
  - Tables: mom_action_items
  - Query: `SELECT COUNT(*) AS total FROM mom_action_items ai WHERE {...}`
- SQL (execute_query) app/meetings/router.py:727-746
  - Tables: mom_action_comments, mom_action_items, mom_meetings
  - Query: `SELECT ai.*, m.title AS meeting_title, m.meeting_date, COALESCE(c.comment_count, 0) AS comment_count FROM mom_action_items ai JOIN mom_meetings m ON m.id = ai.meeting_id LEFT JOIN ( SELECT action_item_id, COUNT(*) AS comment_count FROM mom_action_comments GROUP BY action_item_id ) c ON c.action_item_id = ai.id WHERE {...} ORDER BY ai.{...} {...} NULLS LAST, ai.id ASC LIMIT %s OFFSET %s`

## POST /api/action-items
- Handler: app/meetings/router.py:759-783
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/action-items/{action_id}
- Handler: app/meetings/router.py:865-873
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/action-items/{action_id}
- Handler: app/meetings/router.py:788-860
- SQL (execute_query) app/meetings/router.py:828-832
  - Tables: mom_action_items
  - Query: `SELECT * FROM mom_action_items WHERE id = %s`

## GET /api/action-items/{action_id}/comments
- Handler: app/meetings/router.py:882-911
- SQL (execute_query) app/meetings/router.py:888-892
  - Tables: mom_action_items
  - Query: `SELECT id FROM mom_action_items WHERE id = %s`
- SQL (execute_query) app/meetings/router.py:896-905
  - Tables: mom_action_comments
  - Query: `SELECT id, action_item_id, comment, commented_by_name, created_at FROM mom_action_comments WHERE action_item_id = %s ORDER BY created_at DESC`

## POST /api/action-items/{action_id}/comments
- Handler: app/meetings/router.py:916-947
- SQL (execute_query) app/meetings/router.py:924-928
  - Tables: mom_action_items
  - Query: `SELECT id FROM mom_action_items WHERE id = %s`

## POST /api/admin/backfill-user-roles
- Handler: main.py:1207-1237
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/admin/update-all-passwords
- Handler: main.py:1173-1202
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/application-dropdown
- Handler: app/admin/build_tracker_router.py:1053-1085
- SQL (execute_query) app/admin/build_tracker_router.py:1064-1068
  - Tables: projects
  - Query: `SELECT DISTINCT application_name FROM projects WHERE (tenant_id = %s OR (tenant_id IS NULL AND %s IS NULL)) AND application_name IS NOT NULL ORDER BY application_name`

## GET /api/application-dropdown
- Handler: app/admin/projects_router.py:114-160
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/audits
- Handler: app/audit/router.py:70-121
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/audits
- Handler: app/audit/router.py:164-225
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/audits/{audit_id}
- Handler: app/audit/router.py:269-301
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/audits/{audit_id}
- Handler: app/audit/router.py:125-160
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/audits/{audit_id}
- Handler: app/audit/router.py:229-265
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/audits/{audit_id}/comments
- Handler: app/audit/router.py:305-359
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/auth/change-password
- Handler: main.py:934-1008
- SQL (cursor_execute) main.py:970-970
  - Tables: users
  - Query: `SELECT password FROM users WHERE id = %s`
- SQL (cursor_execute) main.py:991-994
  - Tables: users
  - Query: `UPDATE users SET password = %s, updated_at = NOW() WHERE id = %s`

## GET /api/auth/check-password-change
- Handler: main.py:1012-1065
- SQL (cursor_execute) main.py:1040-1043
  - Tables: users
  - Query: `SELECT password, first_login, last_login FROM users WHERE id = %s`

## POST /api/auth/login
- Handler: main.py:870-918
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/auth/logout
- Handler: main.py:922-925
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/auth/sso/login
- Handler: main.py:1073-1129
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/branding
- Handler: app/email/router.py:125-136
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/bugs
- Handler: app/legacy/bugs.py:456-460
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/bugs
- Handler: app/legacy/qa_dashboard.py:1167-1285
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/bugs
- Handler: app/legacy/bugs.py:473-478
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/bugs/dropdowns
- Handler: app/legacy/bugs.py:431-452
- SQL (execute_query) app/legacy/bugs.py:444-444
  - Tables: (unknown)
  - Query: `{...}`

## GET /api/bugs/export
- Handler: app/legacy/qa_dashboard.py:1421-1551
- SQL (execute_query) app/legacy/qa_dashboard.py:1513-1513
  - Tables: (unknown)
  - Query: `{...}`

## GET /api/bugs/users-dropdown
- Handler: app/legacy/bugs.py:320-409
- SQL (execute_query) app/legacy/bugs.py:355-355
  - Tables: (unknown)
  - Query: `{...}`
- SQL (execute_query) app/legacy/bugs.py:365-365
  - Tables: (unknown)
  - Query: `{...}`
- SQL (execute_query) app/legacy/bugs.py:371-375
  - Tables: (unknown)
  - Query: `SELECT id, full_name, email, department FROM "users" WHERE ("email" = %s OR "id"::text = %s) AND ("is_active" = TRUE) AND ("tenant_id" = %s OR "tenant_id" IS NULL) LIMIT 1`
- SQL (execute_query) app/legacy/bugs.py:384-384
  - Tables: (unknown)
  - Query: `{...}`

## DELETE /api/bugs/{bug_id}
- Handler: app/legacy/bugs.py:498-515
- SQL (execute_query) app/legacy/bugs.py:506-506
  - Tables: (unknown)
  - Query: `{...}`

## GET /api/bugs/{bug_id}
- Handler: app/legacy/bugs.py:464-469
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/bugs/{bug_id}
- Handler: app/legacy/bugs.py:482-494
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/bugs/{bug_id}/upload
- Handler: app/legacy/bugs.py:519-569
- SQL (execute_query) app/legacy/bugs.py:541-541
  - Tables: (unknown)
  - Query: `{...}`

## GET /api/build-numbers
- Handler: app/legacy/qa_master.py:176-197
- SQL (execute_query) app/legacy/qa_master.py:194-194
  - Tables: (unknown)
  - Query: `{...}`

## POST /api/build-numbers
- Handler: app/legacy/qa_master.py:201-221
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/build-numbers/{id}
- Handler: app/legacy/qa_master.py:225-232
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/builds
- Handler: app/admin/build_tracker_router.py:2119-2229
- SQL (execute_query) app/admin/build_tracker_router.py:2135-2139
  - Tables: information_schema.columns
  - Query: `SELECT column_name FROM information_schema.columns WHERE table_name = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:2201-2201
  - Tables: (unknown)
  - Query: `{...}`
- SQL (execute_query) app/admin/build_tracker_router.py:2207-2207
  - Tables: (unknown)
  - Query: `{...}`

## POST /api/builds
- Handler: app/admin/build_tracker_router.py:1099-1270
- SQL (execute_query) app/admin/build_tracker_router.py:1105-1109
  - Tables: information_schema.columns
  - Query: `SELECT column_name FROM information_schema.columns WHERE table_name = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:1117-1121
  - Tables: information_schema.columns
  - Query: `SELECT column_name FROM information_schema.columns WHERE table_name = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:1131-1136
  - Tables: builds
  - Query: `SELECT id FROM builds WHERE project_id = %s AND build_number = %s AND (is_deleted IS NULL OR is_deleted = FALSE) LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1196-1201
  - Tables: builds
  - Query: `SELECT id FROM builds WHERE project_id = %s AND build_number = %s ORDER BY id DESC LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1228-1239
  - Tables: SET, build_reports
  - Query: `INSERT INTO build_reports (build_id, report_type, blocker_count, high_count, medium_count) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (build_id, report_type) DO UPDATE SET blocker_count = EXCLUDED.blocker_count, high_count = EXCLUDED.high_count, medium_count = EXCLUDED.medium_count`
- SQL (execute_query) app/admin/build_tracker_router.py:1241-1241
  - Tables: (unknown)
  - Query: `SELECT id FROM {...} WHERE build_id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1243-1247
  - Tables: (unknown)
  - Query: `UPDATE {...} SET blocker = %s, high = %s, medium = %s, low = %s WHERE build_id = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:1249-1253
  - Tables: (unknown)
  - Query: `INSERT INTO {...} (build_id, blocker, high, medium, low) VALUES (%s, %s, %s, %s, %s)`

## POST /api/builds/draft
- Handler: app/admin/build_tracker_router.py:1274-1332
- SQL (execute_query) app/admin/build_tracker_router.py:1313-1318
  - Tables: builds
  - Query: `SELECT id FROM builds WHERE project_id = %s AND build_number = %s ORDER BY id DESC LIMIT 1`

## GET /api/builds/filters
- Handler: app/admin/build_tracker_router.py:2286-2325
- SQL (execute_query) app/admin/build_tracker_router.py:2291-2295
  - Tables: projects
  - Query: `SELECT DISTINCT application_name FROM projects WHERE (tenant_id = %s OR (tenant_id IS NULL AND %s IS NULL)) ORDER BY application_name ASC`
- SQL (execute_query) app/admin/build_tracker_router.py:2296-2300
  - Tables: projects
  - Query: `SELECT DISTINCT project_owner FROM projects WHERE (tenant_id = %s OR (tenant_id IS NULL AND %s IS NULL)) ORDER BY project_owner ASC`

## GET /api/builds/report
- Handler: app/admin/build_tracker_router.py:1558-1629
- SQL (execute_query) app/admin/build_tracker_router.py:1563-1568
  - Tables: builds
  - Query: `SELECT * FROM builds WHERE project_id = %s ORDER BY build_signoff_date DESC NULLS LAST, id DESC LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1575-1580
  - Tables: functional_reports
  - Query: `SELECT blocker, high, medium, low FROM functional_reports WHERE build_id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1581-1586
  - Tables: automation_reports
  - Query: `SELECT blocker, high, medium, low FROM automation_reports WHERE build_id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1587-1592
  - Tables: cybersecurity_reports
  - Query: `SELECT blocker, high, medium, low FROM cybersecurity_reports WHERE build_id = %s LIMIT 1`

## GET /api/builds/report/aggregate
- Handler: app/admin/build_tracker_router.py:1913-1978
- SQL (execute_query) app/admin/build_tracker_router.py:1928-1928
  - Tables: builds
  - Query: `SELECT id FROM builds WHERE project_id = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:1941-1946
  - Tables: build_reports
  - Query: `SELECT COALESCE(SUM(blocker_count),0) AS blocker, COALESCE(SUM(high_count),0) AS high, COALESCE(SUM(medium_count),0) AS medium FROM build_reports WHERE report_type = 'functional' AND build_id IN ({...})`
- SQL (execute_query) app/admin/build_tracker_router.py:1947-1952
  - Tables: build_reports
  - Query: `SELECT COALESCE(SUM(blocker_count),0) AS blocker, COALESCE(SUM(high_count),0) AS high, COALESCE(SUM(medium_count),0) AS medium FROM build_reports WHERE report_type = 'automation' AND build_id IN ({...})`
- SQL (execute_query) app/admin/build_tracker_router.py:1953-1958
  - Tables: build_reports
  - Query: `SELECT COALESCE(SUM(blocker_count),0) AS blocker, COALESCE(SUM(high_count),0) AS high, COALESCE(SUM(medium_count),0) AS medium FROM build_reports WHERE report_type = 'cybersecurity' AND build_id IN ({...})`

## DELETE /api/builds/{build_id}
- Handler: app/admin/build_tracker_router.py:1708-1756
- SQL (execute_query) app/admin/build_tracker_router.py:1714-1718
  - Tables: information_schema.columns
  - Query: `SELECT column_name FROM information_schema.columns WHERE table_name = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:1720-1720
  - Tables: builds
  - Query: `SELECT id, project_id FROM builds WHERE id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1742-1742
  - Tables: builds
  - Query: `UPDATE builds SET {...} WHERE id = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:1744-1744
  - Tables: builds
  - Query: `DELETE FROM builds WHERE id = %s`

## GET /api/builds/{build_id}
- Handler: app/admin/build_tracker_router.py:2233-2282
- SQL (execute_query) app/admin/build_tracker_router.py:2239-2243
  - Tables: information_schema.columns
  - Query: `SELECT column_name FROM information_schema.columns WHERE table_name = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:2245-2263
  - Tables: public.builds, public.projects
  - Query: `SELECT b.*, p.application_name AS project_name, CASE WHEN b.signoff_status IN ('Go','Conditional-Go','No-Go','Build Rejected') OR b.build_signoff_date IS NOT NULL THEN 'Testing Complete' ELSE 'Testing In Progress' END AS stage FROM public.builds b LEFT JOIN public.projects p ON p.id::text = b.project_id::text WHERE b.id::text = %s LIMIT 1`

## PUT /api/builds/{build_id}
- Handler: app/admin/build_tracker_router.py:1761-1909
- SQL (execute_query) app/admin/build_tracker_router.py:1767-1771
  - Tables: information_schema.columns
  - Query: `SELECT column_name FROM information_schema.columns WHERE table_name = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:1805-1805
  - Tables: builds
  - Query: `SELECT project_id FROM builds WHERE id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1809-1814
  - Tables: builds
  - Query: `SELECT id FROM builds WHERE project_id = %s AND build_number = %s AND id <> %s AND (is_deleted IS NULL OR is_deleted = FALSE) LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1863-1874
  - Tables: SET, build_reports
  - Query: `INSERT INTO build_reports (build_id, report_type, blocker_count, high_count, medium_count) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (build_id, report_type) DO UPDATE SET blocker_count = EXCLUDED.blocker_count, high_count = EXCLUDED.high_count, medium_count = EXCLUDED.medium_count`
- SQL (execute_query) app/admin/build_tracker_router.py:1876-1876
  - Tables: (unknown)
  - Query: `SELECT id FROM {...} WHERE build_id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1878-1882
  - Tables: (unknown)
  - Query: `UPDATE {...} SET blocker = %s, high = %s, medium = %s, low = %s WHERE build_id = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:1884-1888
  - Tables: (unknown)
  - Query: `INSERT INTO {...} (build_id, blocker, high, medium, low) VALUES (%s, %s, %s, %s, %s)`

## GET /api/builds/{build_id}/comments
- Handler: app/admin/build_tracker_router.py:336-367
- SQL (execute_query) app/admin/build_tracker_router.py:351-356
  - Tables: public.builds
  - Query: `SELECT comments FROM public.builds WHERE id = %s AND is_deleted = FALSE`

## GET /api/builds/{build_id}/comments
- Handler: app/admin/build_tracker_router.py:2331-2355
- SQL (execute_query) app/admin/build_tracker_router.py:2340-2340
  - Tables: builds
  - Query: `SELECT comments FROM builds WHERE id = %s LIMIT 1`

## POST /api/builds/{build_id}/comments
- Handler: app/admin/build_tracker_router.py:2360-2400
- SQL (execute_query) app/admin/build_tracker_router.py:2372-2377
  - Tables: public.builds
  - Query: `SELECT comments FROM public.builds WHERE id = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:2391-2395
  - Tables: public.builds
  - Query: `UPDATE public.builds SET comments = %s WHERE id = %s`

## GET /api/builds/{build_id}/report
- Handler: app/admin/build_tracker_router.py:1634-1703
- SQL (execute_query) app/admin/build_tracker_router.py:1639-1644
  - Tables: builds
  - Query: `SELECT * FROM builds WHERE id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1650-1655
  - Tables: functional_test_reports
  - Query: `SELECT blocker, high, medium, low FROM functional_test_reports WHERE build_id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1656-1661
  - Tables: automation_test_reports
  - Query: `SELECT blocker, high, medium, low FROM automation_test_reports WHERE build_id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1662-1667
  - Tables: cybersecurity_reports
  - Query: `SELECT blocker, high, medium, low FROM cybersecurity_reports WHERE build_id = %s LIMIT 1`

## POST /api/builds/{build_id}/reports/{report_type}
- Handler: app/admin/build_tracker_router.py:1336-1464
- SQL (execute_query) app/admin/build_tracker_router.py:1356-1356
  - Tables: builds
  - Query: `SELECT id, project_id FROM builds WHERE id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1388-1393
  - Tables: builds
  - Query: `SELECT id FROM builds WHERE project_id = %s AND build_number = %s ORDER BY id DESC LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1399-1410
  - Tables: SET, build_reports
  - Query: `INSERT INTO build_reports (build_id, report_type, blocker_count, high_count, medium_count) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (build_id, report_type) DO UPDATE SET blocker_count = EXCLUDED.blocker_count, high_count = EXCLUDED.high_count, medium_count = EXCLUDED.medium_count`
- SQL (execute_query) app/admin/build_tracker_router.py:1412-1412
  - Tables: functional_test_reports
  - Query: `SELECT id FROM functional_test_reports WHERE build_id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1414-1418
  - Tables: functional_test_reports
  - Query: `UPDATE functional_test_reports SET blocker = %s, high = %s, medium = %s, low = %s WHERE build_id = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:1420-1424
  - Tables: functional_test_reports
  - Query: `INSERT INTO functional_test_reports (build_id, blocker, high, medium, low) VALUES (%s, %s, %s, %s, %s)`
- SQL (execute_query) app/admin/build_tracker_router.py:1426-1426
  - Tables: automation_test_reports
  - Query: `SELECT id FROM automation_test_reports WHERE build_id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1428-1432
  - Tables: automation_test_reports
  - Query: `UPDATE automation_test_reports SET blocker = %s, high = %s, medium = %s, low = %s WHERE build_id = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:1434-1438
  - Tables: automation_test_reports
  - Query: `INSERT INTO automation_test_reports (build_id, blocker, high, medium, low) VALUES (%s, %s, %s, %s, %s)`
- SQL (execute_query) app/admin/build_tracker_router.py:1440-1440
  - Tables: cybersecurity_reports
  - Query: `SELECT id FROM cybersecurity_reports WHERE build_id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1442-1446
  - Tables: cybersecurity_reports
  - Query: `UPDATE cybersecurity_reports SET blocker = %s, high = %s, medium = %s, low = %s WHERE build_id = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:1448-1452
  - Tables: cybersecurity_reports
  - Query: `INSERT INTO cybersecurity_reports (build_id, blocker, high, medium, low) VALUES (%s, %s, %s, %s, %s)`

## GET /api/builds/{build_id}/signoff
- Handler: app/admin/build_tracker_router.py:735-813
- SQL (execute_query) app/admin/build_tracker_router.py:742-747
  - Tables: build_signoffs
  - Query: `SELECT * FROM build_signoffs WHERE build_id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:754-759
  - Tables: builds
  - Query: `SELECT signoff_status, build_signoff_date, total_bugs, open_bugs FROM builds WHERE id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:764-769
  - Tables: functional_test_reports
  - Query: `SELECT blocker, high, medium, low FROM functional_test_reports WHERE build_id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:770-775
  - Tables: automation_test_reports
  - Query: `SELECT blocker, high, medium, low FROM automation_test_reports WHERE build_id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:776-781
  - Tables: cybersecurity_reports
  - Query: `SELECT blocker, high, medium, low FROM cybersecurity_reports WHERE build_id = %s LIMIT 1`

## POST /api/builds/{build_id}/signoff
- Handler: app/admin/build_tracker_router.py:818-943
- SQL (execute_query) app/admin/build_tracker_router.py:856-856
  - Tables: build_signoffs
  - Query: `SELECT id FROM build_signoffs WHERE build_id = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:892-892
  - Tables: (unknown)
  - Query: `SELECT id FROM {...} WHERE build_id = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:894-898
  - Tables: (unknown)
  - Query: `UPDATE {...} SET blocker=%s, high=%s, medium=%s, low=%s WHERE build_id=%s`
- SQL (execute_query) app/admin/build_tracker_router.py:900-904
  - Tables: (unknown)
  - Query: `INSERT INTO {...} (build_id, blocker, high, medium, low) VALUES (%s, %s, %s, %s, %s)`
- SQL (execute_query) app/admin/build_tracker_router.py:913-924
  - Tables: SET, build_reports
  - Query: `INSERT INTO build_reports (build_id, report_type, blocker_count, high_count, medium_count) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (build_id, report_type) DO UPDATE SET blocker_count = EXCLUDED.blocker_count, high_count = EXCLUDED.high_count, medium_count = EXCLUDED.medium_count`

## GET /api/builds/{build_id}/tasks
- Handler: app/admin/build_tracker_router.py:947-967
- SQL (execute_query) app/admin/build_tracker_router.py:951-955
  - Tables: public.build_tasks
  - Query: `SELECT id, resource_name, task_assigned, COALESCE(spent_hours, 0) AS spent_hours, task_type, COALESCE(task_status, 'Yet to start') as task_status, created_at FROM public.build_tasks WHERE build_id = %s ORDER BY id ASC`

## GET /api/builds/{build_id}/tasks
- Handler: app/admin/build_tracker_router.py:1467-1487
- SQL (execute_query) app/admin/build_tracker_router.py:1471-1475
  - Tables: public.build_tasks
  - Query: `SELECT id, resource_name, task_assigned, COALESCE(spent_hours, 0) AS spent_hours, created_at FROM public.build_tasks WHERE build_id = %s ORDER BY id ASC`

## POST /api/builds/{build_id}/tasks
- Handler: app/admin/build_tracker_router.py:971-1047
- SQL (execute_query) app/admin/build_tracker_router.py:979-979
  - Tables: builds
  - Query: `SELECT id, project_id FROM builds WHERE id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:983-983
  - Tables: projects
  - Query: `SELECT qa_resource_count FROM projects WHERE id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1029-1029
  - Tables: public.build_tasks
  - Query: `DELETE FROM public.build_tasks WHERE build_id = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:1031-1035
  - Tables: public.build_tasks
  - Query: `INSERT INTO public.build_tasks (build_id, resource_name, task_assigned, spent_hours, task_type, task_status) VALUES (%s, %s, %s, %s, %s, %s)`

## POST /api/builds/{build_id}/tasks
- Handler: app/admin/build_tracker_router.py:1490-1555
- SQL (execute_query) app/admin/build_tracker_router.py:1498-1498
  - Tables: builds
  - Query: `SELECT id, project_id FROM builds WHERE id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1502-1502
  - Tables: projects
  - Query: `SELECT qa_resource_count FROM projects WHERE id = %s LIMIT 1`
- SQL (execute_query) app/admin/build_tracker_router.py:1537-1537
  - Tables: public.build_tasks
  - Query: `DELETE FROM public.build_tasks WHERE build_id = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:1539-1543
  - Tables: public.build_tasks
  - Query: `INSERT INTO public.build_tasks (build_id, resource_name, task_assigned, spent_hours) VALUES (%s, %s, %s, %s)`

## GET /api/builds/{build_id}/time-entries
- Handler: app/admin/build_tracker_router.py:282-332
- SQL (execute_query) app/admin/build_tracker_router.py:299-303
  - Tables: information_schema.columns
  - Query: `SELECT column_name FROM information_schema.columns WHERE table_name = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:309-309
  - Tables: (unknown)
  - Query: `{...}`
- SQL (execute_query) app/admin/build_tracker_router.py:314-318
  - Tables: information_schema.columns
  - Query: `SELECT column_name FROM information_schema.columns WHERE table_name = %s AND table_schema = 'public'`
- SQL (execute_query) app/admin/build_tracker_router.py:329-329
  - Tables: (unknown)
  - Query: `{...}`

## POST /api/builds/{build_id}/time-entries
- Handler: app/admin/build_tracker_router.py:673-731
- SQL (execute_query) app/admin/build_tracker_router.py:698-702
  - Tables: information_schema.columns
  - Query: `SELECT column_name FROM information_schema.columns WHERE table_name = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:708-708
  - Tables: (unknown)
  - Query: `{...}`
- SQL (execute_query) app/admin/build_tracker_router.py:711-715
  - Tables: information_schema.columns
  - Query: `SELECT column_name FROM information_schema.columns WHERE table_name = %s AND table_schema = 'public'`
- SQL (execute_query) app/admin/build_tracker_router.py:730-730
  - Tables: (unknown)
  - Query: `{...}`

## GET /api/charts/ageing
- Handler: app/legacy/qa_dashboard.py:704-762
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/charts/assignee
- Handler: app/legacy/qa_dashboard.py:641-701
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/charts/builds
- Handler: app/dashboards/efforttracker_router.py:1262-1353
- SQL (execute_query) app/dashboards/efforttracker_router.py:1320-1320
  - Tables: (unknown)
  - Query: `{...}`

## GET /api/charts/priority
- Handler: app/legacy/qa_dashboard.py:766-796
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/charts/resource-allocation
- Handler: app/dashboards/efforttracker_router.py:1069-1184
- SQL (execute_query) app/dashboards/efforttracker_router.py:1133-1133
  - Tables: (unknown)
  - Query: `{...}`

## GET /api/charts/severity
- Handler: app/legacy/qa_dashboard.py:488-543
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/charts/status
- Handler: app/dashboards/efforttracker_router.py:961-1066
- SQL (execute_query) app/dashboards/efforttracker_router.py:1053-1053
  - Tables: (unknown)
  - Query: `{...}`

## GET /api/charts/status
- Handler: app/legacy/qa_dashboard.py:547-580
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/charts/trend
- Handler: app/legacy/qa_dashboard.py:800-900
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/charts/user-hours
- Handler: app/dashboards/efforttracker_router.py:1187-1259
- SQL (execute_query) app/dashboards/efforttracker_router.py:1244-1244
  - Tables: (unknown)
  - Query: `{...}`

## GET /api/compliance-tasks
- Handler: app/compliance_tasks/router.py:36-85
- SQL (execute_query) app/compliance_tasks/router.py:57-57
  - Tables: (unknown)
  - Query: `{...}`
- SQL (execute_query) app/compliance_tasks/router.py:80-80
  - Tables: (unknown)
  - Query: `{...}`

## POST /api/compliance-tasks
- Handler: app/compliance_tasks/router.py:185-291
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/compliance-tasks/control/{control_id}
- Handler: app/compliance_tasks/router.py:89-131
- SQL (execute_query) app/compliance_tasks/router.py:108-108
  - Tables: (unknown)
  - Query: `{...}`
- SQL (execute_query) app/compliance_tasks/router.py:126-126
  - Tables: (unknown)
  - Query: `{...}`

## DELETE /api/compliance-tasks/{task_id}
- Handler: app/compliance_tasks/router.py:341-371
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/compliance-tasks/{task_id}
- Handler: app/compliance_tasks/router.py:135-181
- SQL (execute_query) app/compliance_tasks/router.py:156-156
  - Tables: (unknown)
  - Query: `{...}`
- SQL (execute_query) app/compliance_tasks/router.py:174-174
  - Tables: (unknown)
  - Query: `{...}`

## PUT /api/compliance-tasks/{task_id}
- Handler: app/compliance_tasks/router.py:295-337
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/compliance-tasks/{task_id}/comments
- Handler: app/compliance_tasks/router.py:375-432
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/configurations
- Handler: app/email/router.py:159-163
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/configurations
- Handler: app/email/router.py:168-190
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/configurations/test
- Handler: app/email/router.py:233-244
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/configurations/{config_id}
- Handler: app/email/router.py:218-228
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/configurations/{config_id}
- Handler: app/email/router.py:195-213
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/configurations/{config_id}/test
- Handler: app/email/router.py:249-259
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/counts
- Handler: app/dashboards/router.py:73-102
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/dashboard-metrics
- Handler: app/meetings/router.py:281-392
- SQL (execute_query) app/meetings/router.py:316-325
  - Tables: mom_action_items
  - Query: `SELECT ai.status, COUNT(*) AS cnt FROM mom_action_items ai WHERE {...} GROUP BY ai.status`
- SQL (execute_query) app/meetings/router.py:336-345
  - Tables: mom_action_items, mom_meetings
  - Query: `SELECT COUNT(DISTINCT m.id) AS total FROM mom_meetings m JOIN mom_action_items ai ON ai.meeting_id = m.id WHERE {...}`
- SQL (execute_query) app/meetings/router.py:347-351
  - Tables: mom_meetings
  - Query: `SELECT COUNT(*) AS total FROM mom_meetings m WHERE {...}`
- SQL (execute_query) app/meetings/router.py:354-362
  - Tables: mom_action_items
  - Query: `SELECT ai.priority, ai.created_at FROM mom_action_items ai WHERE {...} AND ai.status IN ('OPEN', 'IN_PROGRESS', 'BLOCKED')`

## GET /api/dashboard/certifications/metrics
- Handler: app/dashboards/router.py:671-733
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/dashboard/controls/by-certifications
- Handler: app/dashboards/router.py:504-667
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/dashboard/controls/by-certifications
- Handler: app/dashboards/router.py:504-667
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/dashboard/controls/metrics
- Handler: app/dashboards/router.py:323-435
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/dashboard/kpi/metrics
- Handler: app/dashboards/router.py:737-823
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/dashboard/metrics
- Handler: app/dashboards/router.py:439-499
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/dashboard/tasks/metrics
- Handler: app/dashboards/router.py:178-319
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/dev/bootstrap-user
- Handler: main.py:1140-1168
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/events
- Handler: app/email/router.py:101-106
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/export
- Handler: app/legacy/qa_dashboard.py:1288-1418
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/export
- Handler: app/dashboards/efforttracker_router.py:119-343
- SQL (execute_query) app/dashboards/efforttracker_router.py:156-167
  - Tables: projects
  - Query: `SELECT p.application_name AS application, p.project_owner AS owner, p.qa_spoc AS qa_spoc, p.qa_resource_count AS qa_resource_count, p.arrived_date AS arrived_date, p.expected_closing_date AS expected_closing_date FROM projects p {...} ORDER BY p.application_name ASC`
- SQL (execute_query) app/dashboards/efforttracker_router.py:169-182
  - Tables: builds, projects
  - Query: `SELECT p.application_name AS application, b.build_number AS build_number, b.signoff_status AS status, b.build_arrived_date AS arrived_date, b.build_signoff_date AS signoff_date, b.total_bugs AS total_bugs, b.open_bugs AS open_bugs FROM builds b JOIN projects p ON p.id::text = b.project_id::text {...} ORDER BY p.application_name ASC, b.build_number ASC`
- SQL (execute_query) app/dashboards/efforttracker_router.py:184-195
  - Tables: build_tasks, builds, projects
  - Query: `SELECT p.application_name AS application, b.build_number AS build_number, t.resource_name AS resource_name, t.task_assigned AS task_assigned FROM build_tasks t JOIN builds b ON b.id = t.build_id JOIN projects p ON p.id::text = b.project_id::text {...} ORDER BY p.application_name ASC, b.build_number ASC, t.id ASC`
- SQL (execute_query) app/dashboards/efforttracker_router.py:240-245
  - Tables: builds, projects
  - Query: `SELECT COUNT(b.id) AS total_builds FROM builds b JOIN projects p ON p.id::text = b.project_id::text {...}`
- SQL (execute_query) app/dashboards/efforttracker_router.py:247-252
  - Tables: builds, projects
  - Query: `SELECT COUNT(b.id) AS signed_off FROM builds b JOIN projects p ON p.id::text = b.project_id::text {...} AND b.build_signoff_date IS NOT NULL`
- SQL (execute_query) app/dashboards/efforttracker_router.py:254-261
  - Tables: builds, projects
  - Query: `SELECT COALESCE(SUM(b.total_bugs), 0) AS total_bugs, COALESCE(SUM(b.open_bugs), 0) AS open_bugs FROM builds b JOIN projects p ON p.id::text = b.project_id::text {...}`
- SQL (execute_query) app/dashboards/efforttracker_router.py:265-273
  - Tables: build_reports, builds, projects
  - Query: `SELECT COALESCE(SUM(CASE WHEN br.report_type IN ('functional','automation','cybersecurity') THEN br.high_count ELSE 0 END), 0) AS high_bugs, COALESCE(SUM(CASE WHEN br.report_type IN ('functional','automation','cybersecurity') THEN br.medium_count ELSE 0 END), 0) AS medium_bugs FROM build_reports br JOIN builds b ON b.id = br.build_id JOIN projects p ON p.id::text = b.project_id::text {...}`
- SQL (execute_query) app/dashboards/efforttracker_router.py:276-281
  - Tables: builds, projects
  - Query: `SELECT COUNT(b.id) AS in_progress FROM builds b JOIN projects p ON p.id::text = b.project_id::text {...} AND (b.build_signoff_date IS NULL)`
- SQL (execute_query) app/dashboards/efforttracker_router.py:283-292
  - Tables: projects
  - Query: `SELECT MIN(p.arrived_date) AS arrived_date, MIN(p.expected_closing_date) AS expected_closing_date, (SELECT qa_spoc FROM projects pp {...} ORDER BY qa_spoc NULLS LAST LIMIT 1) AS qa_spoc FROM projects p {...}`
- SQL (execute_query) app/dashboards/efforttracker_router.py:296-304
  - Tables: builds, projects
  - Query: `SELECT COALESCE(b.signoff_status, 'Unknown') AS status, COUNT(*) AS cnt FROM builds b JOIN projects p ON p.id::text = b.project_id::text {...} GROUP BY COALESCE(b.signoff_status, 'Unknown') ORDER BY cnt DESC NULLS LAST LIMIT 1`

## GET /api/hours/analytics
- Handler: app/dashboards/efforttracker_router.py:822-958
- SQL (execute_query) app/dashboards/efforttracker_router.py:873-888
  - Tables: build_time_entries, builds, projects
  - Query: `SELECT COALESCE(NULLIF(bte.user_email, ''), NULLIF(bte.resource_name, ''), 'Unknown') AS user_key, COALESCE(bte.log_date::date, b.build_arrived_date::date) AS work_date, COALESCE(p.application_name, 'Unknown') AS project_name, COALESCE(b.transaction_type, 'Unknown') AS category, COALESCE(bte.hours, 0) AS hours FROM build_time_entries bte JOIN builds b ON b.id = bte.build_id JOIN projects p ON p.id::text = b.project_id::text {...}`

## GET /api/hours/user-vs-project
- Handler: app/dashboards/efforttracker_router.py:679-818
- SQL (execute_query) app/dashboards/efforttracker_router.py:728-744
  - Tables: build_time_entries, builds, projects
  - Query: `SELECT COALESCE(NULLIF(bte.resource_name, ''), NULLIF(bte.user_email, ''), 'Unknown') AS user_key, COALESCE(p.application_name, 'Unknown') AS project_name, COALESCE(SUM(bte.hours), 0) AS total_hours, MAX(bte.log_date) as last_worked FROM build_time_entries bte JOIN builds b ON b.id = bte.build_id JOIN projects p ON p.id::text = b.project_id::text {...} GROUP BY COALESCE(NULLIF(bte.resource_name, ''), NULLIF(bte.user_email, ''), 'Unknown'), COALESCE(p.application_name, 'Unknown')`

## POST /api/invite
- Handler: app/users/router.py:537-634
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/master/build-signoff-status
- Handler: app/legacy/qa_master.py:240-251
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/meetings
- Handler: app/meetings/router.py:401-476
- SQL (execute_query) app/meetings/router.py:444-448
  - Tables: mom_meetings
  - Query: `SELECT COUNT(*) AS total FROM mom_meetings m WHERE {...}`
- SQL (execute_query) app/meetings/router.py:451-468
  - Tables: mom_action_items, mom_meetings
  - Query: `SELECT m.*, COALESCE(p.pending_count, 0) AS pending_actions FROM mom_meetings m LEFT JOIN ( SELECT meeting_id, COUNT(*) AS pending_count FROM mom_action_items WHERE status != 'DONE' GROUP BY meeting_id ) p ON p.meeting_id = m.id WHERE {...} ORDER BY m.{...} {...} LIMIT %s OFFSET %s`

## POST /api/meetings
- Handler: app/meetings/router.py:518-546
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/meetings/{meeting_id}
- Handler: app/meetings/router.py:603-622
- SQL (execute_query) app/meetings/router.py:609-613
  - Tables: mom_meetings
  - Query: `SELECT id FROM mom_meetings WHERE id = %s`
- SQL (execute_query) app/meetings/router.py:617-621
  - Tables: mom_meetings
  - Query: `DELETE FROM mom_meetings WHERE id = %s`

## GET /api/meetings/{meeting_id}
- Handler: app/meetings/router.py:481-513
- SQL (execute_query) app/meetings/router.py:487-491
  - Tables: mom_meetings
  - Query: `SELECT * FROM mom_meetings WHERE id = %s`
- SQL (execute_query) app/meetings/router.py:495-509
  - Tables: mom_action_comments, mom_action_items
  - Query: `SELECT ai.*, COALESCE(c.comment_count, 0) AS comment_count FROM mom_action_items ai LEFT JOIN ( SELECT action_item_id, COUNT(*) AS comment_count FROM mom_action_comments GROUP BY action_item_id ) c ON c.action_item_id = ai.id WHERE ai.meeting_id = %s ORDER BY ai.sort_order ASC, ai.id ASC`

## PUT /api/meetings/{meeting_id}
- Handler: app/meetings/router.py:551-598
- SQL (execute_query) app/meetings/router.py:558-562
  - Tables: mom_meetings
  - Query: `SELECT * FROM mom_meetings WHERE id = %s`

## GET /api/notifications
- Handler: app/email/router.py:266-270
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/notifications
- Handler: app/email/router.py:275-295
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/permissions/check
- Handler: app/roles/router.py:302-319
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/permissions/dashboards
- Handler: app/roles/router.py:258-299
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/permissions/modules
- Handler: app/roles/router.py:248-255
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/pivot/status-defect-type
- Handler: app/legacy/qa_dashboard.py:584-639
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/priority-stats
- Handler: app/dashboards/router.py:138-174
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/products
- Handler: app/legacy/bugs.py:413-427
- SQL (execute_query) app/legacy/bugs.py:425-425
  - Tables: (unknown)
  - Query: `{...}`

## GET /api/project-components
- Handler: app/legacy/qa_master.py:131-137
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/project-components
- Handler: app/legacy/qa_master.py:141-147
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/project-components/{id}
- Handler: app/legacy/qa_master.py:161-168
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/project-components/{id}
- Handler: app/legacy/qa_master.py:151-157
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/project-health
- Handler: app/legacy/qa_dashboard.py:1065-1164
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/project/{project_id}
- Handler: app/admin/testcase_router.py:151-171
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/project/{project_id}/filters
- Handler: app/admin/testcase_router.py:141-146
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/projects
- Handler: app/admin/testcase_router.py:121-137
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/projects
- Handler: app/legacy/convex_dashboard.py:191-234
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/projects
- Handler: app/legacy/qa_dashboard.py:374-410
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/projects/{project_id}/overall-report
- Handler: app/admin/build_tracker_router.py:2019-2099
- SQL (execute_query) app/admin/build_tracker_router.py:2028-2032
  - Tables: builds
  - Query: `SELECT id FROM builds WHERE project_id = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:2047-2052
  - Tables: functional_test_reports
  - Query: `SELECT COALESCE(SUM(blocker),0) AS blocker, COALESCE(SUM(high),0) AS high, COALESCE(SUM(medium),0) AS medium, COALESCE(SUM(low),0) AS low FROM functional_test_reports WHERE build_id IN ({...})`
- SQL (execute_query) app/admin/build_tracker_router.py:2053-2058
  - Tables: automation_test_reports
  - Query: `SELECT COALESCE(SUM(blocker),0) AS blocker, COALESCE(SUM(high),0) AS high, COALESCE(SUM(medium),0) AS medium, COALESCE(SUM(low),0) AS low FROM automation_test_reports WHERE build_id IN ({...})`
- SQL (execute_query) app/admin/build_tracker_router.py:2059-2064
  - Tables: cybersecurity_reports
  - Query: `SELECT COALESCE(SUM(blocker),0) AS blocker, COALESCE(SUM(high),0) AS high, COALESCE(SUM(medium),0) AS medium, COALESCE(SUM(low),0) AS low FROM cybersecurity_reports WHERE build_id IN ({...})`

## GET /api/providers
- Handler: app/email/router.py:111-113
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/roles
- Handler: app/roles/router.py:30-50
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/roles
- Handler: app/roles/router.py:113-143
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/roles/{role_id}
- Handler: app/roles/router.py:54-109
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/roles/{role_id}
- Handler: app/roles/router.py:147-205
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/roles/{role_id}/permissions
- Handler: app/roles/router.py:209-245
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/security-controls
- Handler: app/audit/controls_router.py:166-252
- SQL (execute_query) app/audit/controls_router.py:194-194
  - Tables: (unknown)
  - Query: `{...}`
- SQL (execute_query) app/audit/controls_router.py:213-213
  - Tables: (unknown)
  - Query: `{...}`

## POST /api/security-controls
- Handler: app/audit/controls_router.py:338-479
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/security-controls/certifications/unique
- Handler: app/audit/controls_router.py:109-162
- SQL (execute_query) app/audit/controls_router.py:121-121
  - Tables: (unknown)
  - Query: `{...}`
- SQL (execute_query) app/audit/controls_router.py:134-134
  - Tables: (unknown)
  - Query: `{...}`
- SQL (execute_query) app/audit/controls_router.py:144-144
  - Tables: (unknown)
  - Query: `{...}`

## DELETE /api/security-controls/{record_id}
- Handler: app/audit/controls_router.py:670-736
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/security-controls/{record_id}
- Handler: app/audit/controls_router.py:256-334
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/security-controls/{record_id}
- Handler: app/audit/controls_router.py:483-666
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/security-controls/{record_id}/comments
- Handler: app/audit/controls_router.py:947-979
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/security-controls/{record_id}/comments
- Handler: app/audit/controls_router.py:853-943
- SQL: (none detected in handler body; may be in called services/repositories)

## PATCH /api/security-controls/{record_id}/status
- Handler: app/audit/controls_router.py:739-849
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/security-controls/{record_id}/tasks
- Handler: app/audit/controls_router.py:983-1044
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/snapshots/generate
- Handler: app/legacy/qa_dashboard.py:1035-1061
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/snapshots/trend
- Handler: app/legacy/qa_dashboard.py:905-1030
- SQL (execute_query) app/legacy/qa_dashboard.py:1003-1003
  - Tables: (unknown)
  - Query: `{...}`

## GET /api/sprints
- Handler: app/legacy/qa_master.py:86-92
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/sprints
- Handler: app/legacy/qa_master.py:96-102
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/sprints/{id}
- Handler: app/legacy/qa_master.py:116-123
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/sprints/{id}
- Handler: app/legacy/qa_master.py:106-112
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/stats
- Handler: app/dashboards/efforttracker_router.py:21-115
- SQL (execute_query) app/dashboards/efforttracker_router.py:99-99
  - Tables: (unknown)
  - Query: `{...}`

## GET /api/stats
- Handler: app/legacy/qa_dashboard.py:413-484
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/task-tracker
- Handler: app/admin/build_tracker_router.py:371-472
- SQL (execute_query) app/admin/build_tracker_router.py:389-393
  - Tables: information_schema.columns
  - Query: `SELECT column_name FROM information_schema.columns WHERE table_name = %s AND table_schema = 'public'`
- SQL (execute_query) app/admin/build_tracker_router.py:432-432
  - Tables: (unknown)
  - Query: `{...}`
- SQL (execute_query) app/admin/build_tracker_router.py:448-448
  - Tables: builds
  - Query: `SELECT id FROM builds WHERE id = %s LIMIT 1`

## GET /api/tasks
- Handler: app/tasks/router.py:109-147
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/tasks
- Handler: app/tasks/router.py:159-161
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/tasks/categories
- Handler: app/tasks/router.py:28-31
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/tasks/dashboard/by-category
- Handler: app/tasks/router.py:78-82
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/tasks/dashboard/by-owner
- Handler: app/tasks/router.py:69-73
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/tasks/dashboard/overdue
- Handler: app/tasks/router.py:45-52
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/tasks/dashboard/recent-activity
- Handler: app/tasks/router.py:87-94
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/tasks/dashboard/stale
- Handler: app/tasks/router.py:57-64
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/tasks/dashboard/summary
- Handler: app/tasks/router.py:36-40
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/tasks/reference
- Handler: app/tasks/router.py:21-23
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/tasks/status-transitions/{task_id}
- Handler: app/tasks/router.py:99-101
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/tasks/{task_id}
- Handler: app/tasks/router.py:196-198
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/tasks/{task_id}
- Handler: app/tasks/router.py:152-154
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/tasks/{task_id}
- Handler: app/tasks/router.py:166-172
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/tasks/{task_id}/comments
- Handler: app/tasks/router.py:203-205
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/tasks/{task_id}/comments
- Handler: app/tasks/router.py:210-216
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/tasks/{task_id}/history
- Handler: app/tasks/router.py:221-223
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/tasks/{task_id}/start-work
- Handler: app/tasks/router.py:177-179
- SQL: (none detected in handler body; may be in called services/repositories)

## PATCH /api/tasks/{task_id}/status
- Handler: app/tasks/router.py:184-191
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/tasks/{task_id}/workflow
- Handler: app/workflows/router.py:97-106
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/tasks/{task_id}/workflow/advance
- Handler: app/workflows/router.py:111-134
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/teams
- Handler: app/admin/teams_router.py:20-25
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/teams
- Handler: app/admin/teams_router.py:29-57
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/teams/{team_id}
- Handler: app/admin/teams_router.py:84-93
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/teams/{team_id}
- Handler: app/admin/teams_router.py:61-80
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/teams/{team_id}/projects
- Handler: app/admin/teams_router.py:150-161
- SQL (execute_query) app/admin/teams_router.py:160-160
  - Tables: (unknown)
  - Query: `{...}`

## POST /api/teams/{team_id}/projects
- Handler: app/admin/teams_router.py:165-188
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/teams/{team_id}/projects/{project_id}
- Handler: app/admin/teams_router.py:192-198
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/teams/{team_id}/users
- Handler: app/admin/teams_router.py:97-108
- SQL (execute_query) app/admin/teams_router.py:107-107
  - Tables: (unknown)
  - Query: `{...}`

## POST /api/teams/{team_id}/users
- Handler: app/admin/teams_router.py:112-136
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/teams/{team_id}/users/{user_id}
- Handler: app/admin/teams_router.py:140-146
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/template-variables
- Handler: app/email/router.py:118-120
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/templates
- Handler: app/email/router.py:302-306
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/templates
- Handler: app/email/router.py:335-351
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/templates/default/create-ticket
- Handler: app/email/router.py:141-152
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/templates/{template_id}
- Handler: app/email/router.py:373-383
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/templates/{template_id}
- Handler: app/email/router.py:356-368
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/time-entries
- Handler: app/admin/build_tracker_router.py:551-669
- SQL (execute_query) app/admin/build_tracker_router.py:563-567
  - Tables: information_schema.columns
  - Query: `SELECT column_name FROM information_schema.columns WHERE table_name = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:569-573
  - Tables: information_schema.columns
  - Query: `SELECT column_name FROM information_schema.columns WHERE table_name = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:576-580
  - Tables: information_schema.columns
  - Query: `SELECT column_name FROM information_schema.columns WHERE table_name = %s AND table_schema = 'public'`
- SQL (execute_query) app/admin/build_tracker_router.py:653-653
  - Tables: (unknown)
  - Query: `{...}`
- SQL (execute_query) app/admin/build_tracker_router.py:659-659
  - Tables: (unknown)
  - Query: `{...}`

## DELETE /api/time-entries/{entry_id}
- Handler: app/admin/build_tracker_router.py:528-547
- SQL (execute_query) app/admin/build_tracker_router.py:536-536
  - Tables: build_time_entries
  - Query: `SELECT * FROM build_time_entries WHERE id = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:541-541
  - Tables: build_time_entries
  - Query: `DELETE FROM build_time_entries WHERE id = %s`

## PUT /api/time-entries/{entry_id}
- Handler: app/admin/build_tracker_router.py:476-524
- SQL (execute_query) app/admin/build_tracker_router.py:486-486
  - Tables: build_time_entries
  - Query: `SELECT * FROM build_time_entries WHERE id = %s`
- SQL (execute_query) app/admin/build_tracker_router.py:518-518
  - Tables: (unknown)
  - Query: `{...}`

## POST /api/upload
- Handler: app/admin/testcase_router.py:27-117
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/users
- Handler: app/users/router.py:160-193
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/users
- Handler: app/users/router.py:197-287
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/users/dropdown
- Handler: app/legacy/bugs.py:308-316
- SQL (execute_query) app/legacy/bugs.py:313-313
  - Tables: (unknown)
  - Query: `{...}`

## GET /api/users/dropdown
- Handler: app/users/router.py:146-156
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/users/search
- Handler: app/users/router.py:119-142
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/users/{user_id}
- Handler: app/users/router.py:479-533
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/users/{user_id}
- Handler: app/users/router.py:291-332
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/users/{user_id}
- Handler: app/users/router.py:336-475
- SQL (execute_query) app/users/router.py:366-375
  - Tables: users
  - Query: `UPDATE users SET password = %s, updated_at = %s WHERE id = %s RETURNING id, email`
- SQL (execute_query) app/users/router.py:379-383
  - Tables: users
  - Query: `SELECT password FROM users WHERE id = %s LIMIT 1`

## GET /api/users/{user_id}/roles
- Handler: app/users/router.py:637-693
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/users/{user_id}/roles
- Handler: app/users/router.py:697-729
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/users/{user_id}/roles/{role_id}
- Handler: app/users/router.py:733-763
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/waterfall/json
- Handler: app/legacy/convex_dashboard.py:144-186
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/workflows
- Handler: app/workflows/router.py:18-20
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/workflows
- Handler: app/workflows/router.py:53-55
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/workflows/mappings
- Handler: app/workflows/router.py:24-26
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/workflows/mappings
- Handler: app/workflows/router.py:30-37
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/workflows/mappings/{mapping_id}
- Handler: app/workflows/router.py:41-43
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/workflows/{workflow_id}
- Handler: app/workflows/router.py:69-71
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/workflows/{workflow_id}
- Handler: app/workflows/router.py:47-49
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/workflows/{workflow_id}
- Handler: app/workflows/router.py:59-65
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/workflows/{workflow_id}/activate
- Handler: app/workflows/router.py:75-77
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/workflows/{workflow_id}/clone
- Handler: app/workflows/router.py:87-89
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/workflows/{workflow_id}/deactivate
- Handler: app/workflows/router.py:81-83
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/{id}
- Handler: app/admin/projects_router.py:458-488
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/{id}
- Handler: app/legacy/incident_register.py:158-184
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/{id}
- Handler: app/legacy/risk_register.py:170-196
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/{id}
- Handler: app/meetings/mrm_router.py:152-177
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/{id}
- Handler: app/admin/projects_router.py:208-291
- SQL (execute_query) app/admin/projects_router.py:242-247
  - Tables: builds
  - Query: `SELECT * FROM builds WHERE project_id = %s ORDER BY build_arrived_date DESC NULLS LAST, id DESC LIMIT 1`
- SQL (execute_query) app/admin/projects_router.py:256-261
  - Tables: functional_test_reports
  - Query: `SELECT blocker, high, medium, low FROM functional_test_reports WHERE build_id = %s LIMIT 1`
- SQL (execute_query) app/admin/projects_router.py:262-267
  - Tables: automation_test_reports
  - Query: `SELECT blocker, high, medium, low FROM automation_test_reports WHERE build_id = %s LIMIT 1`
- SQL (execute_query) app/admin/projects_router.py:268-273
  - Tables: cybersecurity_reports
  - Query: `SELECT blocker, high, medium, low FROM cybersecurity_reports WHERE build_id = %s LIMIT 1`
- SQL (execute_query) app/admin/projects_router.py:280-284
  - Tables: build_tasks
  - Query: `SELECT resource_name, task_assigned, task_type, task_status, spent_hours FROM build_tasks WHERE build_id = %s`

## GET /api/{id}
- Handler: app/legacy/incident_register.py:108-124
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/{id}
- Handler: app/legacy/risk_register.py:83-103
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/{id}
- Handler: app/meetings/mrm_router.py:102-118
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/{id}
- Handler: app/admin/projects_router.py:377-454
- SQL (execute_query) app/admin/projects_router.py:430-434
  - Tables: projects
  - Query: `SELECT id FROM projects WHERE application_name = %s AND id != %s AND ((tenant_id = %s) OR (tenant_id IS NULL AND %s IS NULL))`

## PUT /api/{id}
- Handler: app/legacy/incident_register.py:128-154
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/{id}
- Handler: app/legacy/risk_register.py:139-165
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/{id}
- Handler: app/meetings/mrm_router.py:122-148
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /api/{testcase_id}
- Handler: app/admin/testcase_router.py:197-203
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/{testcase_id}
- Handler: app/admin/testcase_router.py:175-183
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /api/{testcase_id}
- Handler: app/admin/testcase_router.py:187-193
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/{testcase_id}/activity
- Handler: app/admin/testcase_router.py:207-212
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /api/{testcase_id}/comments
- Handler: app/admin/testcase_router.py:216-221
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /api/{testcase_id}/comments
- Handler: app/admin/testcase_router.py:225-234
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /certifications
- Handler: main.py:480-567
- SQL: (none detected in handler body; may be in called services/repositories)

## POST /certifications
- Handler: main.py:791-800
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /certifications/dropdowns
- Handler: main.py:680-686
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /certifications/dropdowns/{field_name}
- Handler: main.py:690-697
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /certifications/from-controls
- Handler: main.py:572-676
- SQL: (none detected in handler body; may be in called services/repositories)

## DELETE /certifications/{certification_id}
- Handler: main.py:821-831
- SQL: (none detected in handler body; may be in called services/repositories)

## PUT /certifications/{certification_id}
- Handler: main.py:805-816
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /certifications/{certification_name}
- Handler: main.py:702-786
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /dev/test-bcrypt
- Handler: main.py:134-146
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /health
- Handler: main.py:128-129
- SQL: (none detected in handler body; may be in called services/repositories)

## GET /raw-probe
- Handler: main.py:1241-1257
- SQL: (none detected in handler body; may be in called services/repositories)
