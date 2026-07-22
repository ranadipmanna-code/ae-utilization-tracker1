-- ===========================================================================
-- Role-separated selection + evaluation tables
-- Run ONCE in phpMyAdmin: Anudip_AE_Team -> SQL tab -> paste -> Go
--
-- Existing `extended_ae_session_selection` stays as-is (Extended AE claims).
-- These add the Core AE side, plus a split evaluation table per role.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. Core AE session selection
--    Mirrors extended_ae_session_selection, PLUS assigned_extended_ae_email:
--    the Core AE can claim a session and delegate it to one of their
--    Extended AE team members.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `core_ae_session_selection` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `core_ae_email` VARCHAR(100) COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `session_date` DATE NOT NULL,
  `slot_time` VARCHAR(50) COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `module` VARCHAR(50) COLLATE utf8mb4_0900_ai_ci NULL,
  `batch_code` VARCHAR(50) COLLATE utf8mb4_0900_ai_ci NULL,

  -- who this observation is handed to (NULL = the Core AE keeps it)
  `assigned_extended_ae_email` VARCHAR(100) COLLATE utf8mb4_0900_ai_ci NULL,

  `status` VARCHAR(50) COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'Not Selected',
  `updated_on` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_core_pick` (`core_ae_email`, `session_date`, `slot_time`, `batch_code`),
  KEY `idx_core_date` (`core_ae_email`, `session_date`),
  KEY `idx_assigned` (`assigned_extended_ae_email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- ---------------------------------------------------------------------------
-- 2. Core AE evaluation
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `core_ae_evaluation` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `core_ae_email` VARCHAR(100) COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `session_id` VARCHAR(160) COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `trainer_name` VARCHAR(120) COLLATE utf8mb4_0900_ai_ci NULL,
  `trainer_email` VARCHAR(100) COLLATE utf8mb4_0900_ai_ci NULL,
  `session_date` DATE NOT NULL,
  `slot_time` VARCHAR(50) COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `batch_code` VARCHAR(50) COLLATE utf8mb4_0900_ai_ci NULL,
  `module` VARCHAR(50) COLLATE utf8mb4_0900_ai_ci NULL,
  `program_name` VARCHAR(150) COLLATE utf8mb4_0900_ai_ci NULL,
  `duration_minutes` INT NULL,
  `rating` INT NULL,
  `remarks` TEXT COLLATE utf8mb4_0900_ai_ci NULL,
  `status` VARCHAR(30) COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'Completed',
  `created_on` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_on` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_core_eval` (`core_ae_email`, `session_id`),
  KEY `idx_core_eval_date` (`session_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- ---------------------------------------------------------------------------
-- 3. Extended AE evaluation
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `extended_ae_evaluation` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `extended_ae_email` VARCHAR(100) COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `session_id` VARCHAR(160) COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `trainer_name` VARCHAR(120) COLLATE utf8mb4_0900_ai_ci NULL,
  `trainer_email` VARCHAR(100) COLLATE utf8mb4_0900_ai_ci NULL,
  `session_date` DATE NOT NULL,
  `slot_time` VARCHAR(50) COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `batch_code` VARCHAR(50) COLLATE utf8mb4_0900_ai_ci NULL,
  `module` VARCHAR(50) COLLATE utf8mb4_0900_ai_ci NULL,
  `program_name` VARCHAR(150) COLLATE utf8mb4_0900_ai_ci NULL,
  `duration_minutes` INT NULL,
  `rating` INT NULL,
  `remarks` TEXT COLLATE utf8mb4_0900_ai_ci NULL,
  `status` VARCHAR(30) COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'Completed',
  `created_on` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_on` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_ext_eval` (`extended_ae_email`, `session_id`),
  KEY `idx_ext_eval_date` (`session_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- ---------------------------------------------------------------------------
-- 4. OPTIONAL — retire the old combined evaluation table.
--    The app no longer writes to it once the new code is deployed.
--    Uncomment only after you've confirmed the new tables work.
-- ---------------------------------------------------------------------------
-- DROP TABLE IF EXISTS `session_evaluation`;
