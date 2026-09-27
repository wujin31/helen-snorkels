# Draft: request to the Shore Stations team about the underwater cam

One email unlocks the two cam features that wait on Scripps: the inline live
player (built; set `site_embed_url` in `config/sources.yaml`) and cam-derived
visibility on the page (the cam model keeps it private until then).

To: sioshorestation@gmail.com
Subject: Scripps Pier underwater cam: embedding it on a small snorkel-conditions page

Hi Shore Stations team,

I'm Jay, and I work with SIO through SPF. On the side I'm building a small,
non-commercial page that gives my partner a daily "snorkel today?" call for La
Jolla Cove and La Jolla Shores: https://wujin31.github.io/helen-snorkels/.
The underwater cam is the heart of it. The piling guide on the PierViz page
(4, 11, 14 and 30 ft) is the best visibility measurement around.

Two things I'd love your OK on:

1. **Embedding the live player.** The page currently just links to the stream
   on HDOnTap. Would you add `https://wujin31.github.io` to the allowed sites
   for your PierViz embed (`scripps_pier-underwater-CUST`, under Embed Configs
   in the HDOnTap portal)? The player would appear on the page credited to the
   Shore Stations Program, with a link to PierViz.
2. **Reading visibility from the cam.** The page saves one still every 15
   minutes in daylight from the public stream, stored privately and never
   republished. It estimates visibility from how many pilings are visible.
   May the page show that number ("3 of 4 pilings visible, ~11-14 ft")? No
   images, just the reading.

And two questions:

- Is there a preferred way to grab stills (a snapshot URL, an archive, or a
  rate you'd like us to stay under)?
- Would a record of cam-derived visibility be useful to you? I'm happy to
  share it and the code, and to flag outages or lens fouling when the frames
  show them.

Until I hear from you, the page only links to the stream and keeps
cam-derived numbers to itself. If you'd rather we didn't use the stream this
way, I'll stop capture right away.

Thanks,
Jay
