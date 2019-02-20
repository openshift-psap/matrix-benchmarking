/*
Some general notes.

Times spent are in seconds, stored as "DOUBLE PRECISION" allowing nanosecond precision if needed.
Other times, beside the "time" field in experiments are expressed in seconds and stored as
"DOUBLE PRECISION" too but to avoid loosing precision they start from the beginning of the
day of the experiment.

Cascading updates are only for UPDATEs, I prefer to have manually delete instead
of making easier to delete.
*/

/*
DROP TABLE public.client_stats;
DROP TABLE public.host_stats;
DROP TABLE public.guest_stats;
DROP TABLE public.frames;
DROP TABLE public.parameters;
DROP TABLE public.experiments;
*/

/* This table holds information for each experiments done.
 * This table is then linked with other tables to provide information
 * for frames, parameters and so on.
 */
CREATE TABLE public.experiments
(
  /* numeric unique ID */
  id SERIAL PRIMARY KEY,
  /* time the experiment was taken */
  time TIMESTAMP NOT NULL DEFAULT now(),
  /* optional description */
  description TEXT NULL
);
COMMENT ON TABLE public.experiments IS 'Holds information about experiments';
COMMENT ON COLUMN public.experiments.id IS 'id of the experiment';

/* This table holds information for the experiment parameters.
 * Most of the parameters are optional.
 * See also Redmine #47.
 */
CREATE TABLE public.parameters
(
  /* experiment this parameter referes to */
  id_experiment INT REFERENCES experiments(id) ON UPDATE CASCADE,
  /* frames per second */
  FPS INT NULL,
  /* resolution width and height */
  width INT NULL,
  height INT NULL,
  /* group of pictures, used in some encoders like H264 to specify when to encode a full image */
  GOP INT NULL,
  /* bits per seconds */
  bitrate INT NULL,
  /* number of reference frames */
  num_ref_frames INT NULL
  /* TODO quality, GOP pattern */
);
COMMENT ON TABLE public.parameters IS 'Holds information about experiment parameters';

/* This table holds information on the frames during the experiment.
 */
CREATE TABLE public.frames
(
  /* experiment this parameter referes to */
  id_experiment INT REFERENCES experiments(id) ON UPDATE CASCADE,
  /* time before starting capturing on the guest */
  agent_time DOUBLE PRECISION,
  /* size of the compressed frame */
  size INT NOT NULL,
  /* multimedia time, as defined by SPICE, provided by server Here a NUMERIC is used as the number is unsigned */
  mm_time NUMERIC(9) NULL,
  /* time to capture by the guest, in seconds */
  capture_duration DOUBLE PRECISION NULL,
  /* time to encode by the guest, in seconds */
  encode_duration DOUBLE PRECISION NULL,
  /* time to send by the guest, in seconds */
  send_duration DOUBLE PRECISION NOT NULL,
  /* time client received */
  client_time DOUBLE PRECISION NULL,
  /* time frame took to be decoded by the client, in seconds */
  decode_duration DOUBLE PRECISION NULL,
  /* queue size on the client, taken when frame was decoded, in number of frames */
  queue_size INT NULL
);
COMMENT ON TABLE public.frames IS 'Holds information about experiment frames';

/* This table holds information about guest statistics */
CREATE TABLE public.guest_stats
(
  /* experiment this parameter referes to */
  id_experiment INT REFERENCES experiments(id) ON UPDATE CASCADE,
  time DOUBLE PRECISION NOT NULL,
  /* GPU memory used in MB */
  gpu_memory INT NULL,
  /* GPU usage, percentage */
  gpu_usage FLOAT NULL,
  /* encode usage, percentage */
  encode_usage FLOAT NULL,
  /* decode usage, percentage */
  decode_usage FLOAT NULL
);
COMMENT ON TABLE public.guest_stats IS 'Holds information about guest statistics';

/* This table holds information about host statistics */
CREATE TABLE public.host_stats
(
  /* experiment this parameter referes to */
  id_experiment INT REFERENCES experiments(id) ON UPDATE CASCADE,
  time DOUBLE PRECISION NOT NULL,
  /* CPU usage, percentage */
  cpu_usage FLOAT NULL
);
COMMENT ON TABLE public.host_stats IS 'Holds information about host statistics';

/* This table holds information about client statistics */
CREATE TABLE public.client_stats
(
  /* experiment this parameter referes to */
  id_experiment INT REFERENCES experiments(id) ON UPDATE CASCADE,
  time DOUBLE PRECISION NOT NULL,
  /* total GPU usage, percentage */
  gpu_usage FLOAT NULL,
  /* application GPU usage, percentage */
  app_gpu_usage FLOAT NULL,
  /* total CPU usage, percentage */
  cpu_usage FLOAT NULL,
  /* application CPU usage, percentage */
  app_cpu_usage FLOAT NULL
);
COMMENT ON TABLE public.host_stats IS 'Holds information about host statistics';
