-- ===========================================================================
-- CMIS task defaults / slot task assignment  ->  table: ae_slot_task
-- Run ONCE in phpMyAdmin: Anudip_AE_Team -> SQL tab -> paste -> Go
--
-- Each slot in a member's OWN CMIS schedule (upcoming_trainer_utilization_view
-- rows where email_id = their email) has a DEFAULT task DERIVED FROM CMIS via
-- the course alias (c_alias):
--     plr* family (plr_mi1/2, plr_crd1/2, plr_mi_save, PLR_SAVE — the
--                  placement / interview modules)  -> mock_interview
--     anything else (a real course module: ISP, cs_ai, dp_*, java_core, ...)
--                                                   -> teaching
-- The default is IMPLICIT: no row exists for it. A row here exists only when
-- that CMIS default has been overridden, either automatically (the member
-- claimed an Evaluation for that date+slot_time) or manually (Training /
-- Project Involvement / Other, or explicitly pinning a different CMIS type).
-- Deleting the row — or setting task_type back to the slot's own CMIS-derived
-- default — restores the default.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS `ae_slot_task` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `member_email` VARCHAR(100) COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `member_role`  VARCHAR(20)  COLLATE utf8mb4_0900_ai_ci NOT NULL,   -- core_ae / extended_ae
  `session_date` DATE NOT NULL,
  `slot_time`    VARCHAR(50)  COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `slot_name`    VARCHAR(50)  COLLATE utf8mb4_0900_ai_ci NULL,        -- display only, from CMIS

  `task_type` ENUM('mock_interview','teaching',
                   'evaluation','training','project_involvement','other')
              COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'mock_interview',
  `other_note` VARCHAR(255) COLLATE utf8mb4_0900_ai_ci NULL,

  -- when task_type = 'evaluation', points at the row in
  -- core_ae_session_selection / extended_ae_session_selection that caused it
  `ref_selection_id` INT NULL,

  `set_by` VARCHAR(100) COLLATE utf8mb4_0900_ai_ci NULL,
  `updated_on` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_member_slot` (`member_email`, `session_date`, `slot_time`),
  KEY `idx_member_date` (`member_email`, `session_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------------
-- MIGRATION — run this ONLY if you already created ae_slot_task with the old
-- ENUM. It widens task_type to include 'teaching'. Safe to skip if you just
-- ran the CREATE TABLE above for the first time.
-- ---------------------------------------------------------------------------
-- ALTER TABLE `ae_slot_task`
--   MODIFY `task_type` ENUM('mock_interview','teaching',
--                           'evaluation','training','project_involvement','other')
--   COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'mock_interview';
