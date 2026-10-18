## Cold start
A user with <14 days of history or <20 episodes gets NO candidates - the
detector observes silently. Log `{"op":"detector_observing",...}` so the state
is visible in `cle log`.
