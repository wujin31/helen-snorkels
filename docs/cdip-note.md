# Draft: note to CDIP about automated access

To: www@cdip.ucsd.edu
Subject: Access from GitHub Actions for a small La Jolla snorkel-conditions tool

Hi CDIP team,

I'm Jay; I work with SIO through SPF. I've built a small, non-commercial tool
that gives my partner a daily "snorkel today?" call for twelve San Diego snorkel spots, from La
Jolla to Point Loma and North County, and CDIP's MOP nowcasts (one point per
spot, D0317 to D0708) and the Scripps Nearshore buoy (201) are its backbone.
Thank you for them.

It runs on GitHub Actions, and some requests from those runners now get
"Access Denied. Please contact us at www@cdip.ucsd.edu". So I'm getting in touch, as the message asks. What it fetches, all via THREDDS:

- OPeNDAP subsets of the last few hours of the twelve `D0xxx_nowcast.nc` files
  and `201p1_rt.nc`, about once an hour in daylight, plus a 72-hour window
  when it recomputes the call (hourly);
- the MOP forecast files twice a day via fileServer.

Requests identify themselves with the User-Agent
`snorkel-status/0.1 (+https://github.com/wujin31/helen-snorkels)`.

Is there a preferred way or rate for this kind of use, or a way to be
allowlisted? I'm happy to cut it back or switch to whatever endpoint suits you,
and to share the code or the archive if it's useful.

Thanks,
Jay
