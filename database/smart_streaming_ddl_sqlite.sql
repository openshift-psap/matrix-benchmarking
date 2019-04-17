
CREATE TABLE IF NOT EXISTS experiments
(
  id INTEGER UNIQUE PRIMARY KEY AUTOINCREMENT NOT NULL,
  time BIGINT NOT NULL DEFAULT (datetime('now')),
  description TEXT NULL,

  FPS INT NULL,
  width INT NULL,
  height INT NULL,
  GOP INT NULL,
  bitrate INT NULL,
  num_ref_frames INT NULL,

  uuid VARCHAR(40),
  imported BOOLEAN NOT NULL DEFAULT(0)
);

CREATE TABLE IF NOT EXISTS attachments
(
  id_experiment INTEGER,
  name VARCHAR(100) NOT NULL,
  content TEXT NOT NULL,

  CONSTRAINT con_primary_name PRIMARY KEY(id_experiment, name)
  FOREIGN KEY (id_experiment) REFERENCES experiments
);

CREATE TABLE IF NOT EXISTS frames
(
  id_experiment INTEGER,
  agent_time DOUBLE PRECISION,
  size INT NOT NULL,
  mm_time BIGINT NULL,
  capture_duration DOUBLE PRECISION NULL,
  encode_duration DOUBLE PRECISION NULL,
  send_duration DOUBLE PRECISION NOT NULL,
  client_time DOUBLE PRECISION NULL,
  decode_duration DOUBLE PRECISION NULL,
  queue_size INT NULL,

  CONSTRAINT con_primary_name PRIMARY KEY(id_experiment, agent_time)
  FOREIGN KEY (id_experiment) REFERENCES experiments
);

CREATE TABLE IF NOT EXISTS guest_stats
(
  id_experiment INTEGER,
  time DOUBLE PRECISION NOT NULL,
  gpu_memory INT NULL,
  gpu_usage FLOAT NULL,
  encode_usage FLOAT NULL,
  decode_usage FLOAT NULL,

  CONSTRAINT con_primary_name PRIMARY KEY(id_experiment, time)
  FOREIGN KEY (id_experiment) REFERENCES experiments
);

CREATE TABLE IF NOT EXISTS host_stats
(
  id_experiment INTEGER,
  time DOUBLE PRECISION NOT NULL,
  cpu_usage FLOAT NULL,

  CONSTRAINT con_primary_name PRIMARY KEY(id_experiment, time)
  FOREIGN KEY (id_experiment) REFERENCES experiments
);

CREATE TABLE IF NOT EXISTS client_stats
(
  id_experiment INTEGER,
  time DOUBLE PRECISION NOT NULL,
  gpu_usage FLOAT NULL,
  app_gpu_usage FLOAT NULL,
  cpu_usage FLOAT NULL,
  app_cpu_usage FLOAT NULL,

  CONSTRAINT con_primary_name PRIMARY KEY(id_experiment, time)
  FOREIGN KEY (id_experiment) REFERENCES experiments
);

