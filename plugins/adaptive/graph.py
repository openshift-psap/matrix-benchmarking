from ui import UIState

class GraphFormat():

    @staticmethod
    def key_frames_40(Y_lst, X_lst):
        return GraphFormat.key_frames_N(Y_lst, X_lst, 40)

    @staticmethod
    def key_frames_from_qual(Y_lst, X_lst):
        db = UIState().DB
        if not db.feedback: return []

        for ts, src, msg in db.feedback:
            try: pos = msg.index("keyframe-period=")
            except ValueError: continue

            #msg: 'encoding: bitrate=10000;rate-control=vbr;keyframe-period=60;framerate=35

            keyframe_period = int(msg[pos+len("keyframe-period="):].partition(";")[0])

            break
        else: return []

        return GraphFormat.key_frames_N(Y_lst, X_lst, keyframe_period)

    @staticmethod
    def key_frames_N(Y_lst, X_lst, PERIOD):
        first_set = Y_lst[:PERIOD]
        first_kf_pos = first_set.index(max(first_set))

        return [elt if ((pos % PERIOD) == first_kf_pos) else 0
                for pos, elt in enumerate(Y_lst)]

    @staticmethod
    def as_key_frames_period(Y_lst, X_lst):
        return GraphFormat.as_key_frames(Y_lst, X_lst, period=True)

    @staticmethod
    def as_key_frames(Y_lst, X_lst=None, period=False):
        KEY_NORMAL_SIZE_RATIO = 33/100
        MIN_KEYFRAME_PERIOD = 11

        avg_frame_size = statistics.mean(Y_lst)
        max_frame_size = max(Y_lst)
        min_keyframe_size = avg_frame_size + (max_frame_size-avg_frame_size) * KEY_NORMAL_SIZE_RATIO

        keyframe_positions = []
        while True:
            max_size = max(Y_lst)
            max_pos = Y_lst.index(max_size)

            Y_lst[max_pos] = 0

            if max_size < min_keyframe_size:
                # not big enough for a keyframe --> done
                break

            too_close = False
            for kf_pos, kf_size in keyframe_positions:
                if abs(kf_pos - max_pos) < MIN_KEYFRAME_PERIOD:
                    # too close to previous KF
                    too_close = True
                    break

            if too_close: continue

            keyframe_positions.append([max_pos, max_size])


        new = []
        prev_pos = 0
        for pos, val in sorted(keyframe_positions):
            if period:
                if not new:
                    # skip the first one as it's partial
                    value = None
                    prev_pos = pos
                else:
                    kf_dist = pos - prev_pos
                    if kf_dist >= MIN_KEYFRAME_PERIOD:
                        prev_pos = pos
                    else:
                        print("ERROR, keyframe too close!", kf_dist) # should have been detected earlier on
                        # do not change the position of the last keyframe, we're to close
                        kf_dist = new[-1]

                    value = kf_dist
            else:
                value = val

            padding = value if period else 0
            new += [padding] * (pos-len(new)) + [value]

        last_val = None if period else 0

        new += [last_val] * (len(Y_lst)-len(new))

        return new

    @staticmethod
    def as_fps_5s(Y_lst, X_lst):
        return GraphFormat.as_fps_N(Y_lst, X_lst, 5)

    def as_fps_N(Y_lst, X_lst, n):
        from collections import deque
        cache = deque()

        def time_length(_cache):
            l = _cache[-1][0] - _cache[0][0]
            return l.total_seconds()

        enough = False
        new = []
        for x, y in zip(X_lst, Y_lst):
            cache.append((x, y))
            while time_length(cache) >= n:
                cache.popleft()
                enough = True

            if not enough:
                new.append(None)
            else:
                new.append(len(cache) / n)

        return new

    @staticmethod
    def as_delta(Y_lst, X_lst):
        new = [(stop-start).total_seconds() for start, stop in zip (X_lst, X_lst[1:])]
        if new: new.append(new[-1]) # so that len(new) == len(Y_lst)

        return new

    @staticmethod
    def get_setting_modifier(operation_name):
        OPERATIONS = {
            'inverted': lambda x: 1/float(x),
        }

        def modifier(table, X_lst, X_raw, X_idx):
            db = UIState().DB
            qual = iter(db.feedback_by_table[table])
            try: current_qual = next(qual)
            except StopIteration: qual = None
            new = []
            last_value = None

            name, *operations = operation_name

            for x_raw in X_raw:
                while qual and current_qual[0][X_idx] == x_raw:
                    qual_msg = current_qual[1]
                    if qual_msg.startswith("!encoding:") and name in qual_msg:
                        params = qual_msg.partition("params:")[-1].split(';')
                        for param in params:
                            if param.startswith("gst.prop="): param = param.partition("=")[-1]
                            if not param.startswith(name): continue
                            last_value= int(param.split("=")[1])
                            for op in operations:
                                last_value = OPERATIONS[op](last_value)
                            new.append(last_value)
                            break
                    try: current_qual = next(qual)
                    except StopIteration: qual = None
                else:
                    new.append(last_value)
            return new
        return modifier

    @staticmethod
    def per_sec_1(Y_lst, X_lst):
        return GraphFormat.per_sec_N(Y_lst, X_lst, 1)

    @staticmethod
    def per_sec_5(Y_lst, X_lst):
        return GraphFormat.per_sec_N(Y_lst, X_lst, 5)

    @staticmethod
    def per_sec_20(Y_lst, X_lst):
        return GraphFormat.per_sec_N(Y_lst, X_lst, 20)

    @staticmethod
    def per_sec_60(Y_lst, X_lst):
        return GraphFormat.per_sec_N(Y_lst, X_lst, 60)

    @staticmethod
    def per_sec_N(Y_lst, X_lst, n):
        from collections import deque
        cache = deque()

        def time_length(_cache):
            l = _cache[-1][0] - _cache[0][0]
            return l.total_seconds()

        enough = False
        new = []
        for x, y in zip(X_lst, Y_lst):
            cache.append((x, y))
            while time_length(cache) >= n:
                cache.popleft()
                enough = True

            if not enough:
                new.append(None)
            else:
                new.append(sum([y for x,y in cache]) / n)

        return new

    @staticmethod
    def as_it_is(Y_lst, X_lst):
        print(Y_lst)
        return Y_lst
