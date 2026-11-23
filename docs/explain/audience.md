# Audience

## Who it's for

Self: one listener with one music library on the Mac mini. Realistically one user.

## How they use it

On the laptop and phone over Tailscale (the layout has a phone bottom bar and works at 375 px). The jobs: look back at listening (Years, Wrapped, Top, This day), look into the library (what's there, what's played, what's analysed) and check that traqfreq agrees with jimbo-dj (the gate pages on SETUP, HISTORY and LIBRARY).

## Access and accounts

Tailnet only, at http://macmini:4492. No sign-in and no roles: anyone who can reach the tailnet address can read everything. It changes nothing anywhere, so there is nothing an outsider could break.

## What that means for decisions

One library and one listening history are assumed throughout (no multi-user, no onboarding). The listening time zone is one setting. If it were ever shared beyond the tailnet, it would need sign-in first, and once it takes over writes (P6) those actions would need an owner check.
