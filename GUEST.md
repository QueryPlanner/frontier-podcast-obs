# The Frontier Podcast — guest setup

Nothing to install. You need **Chrome or Edge** on a **laptop or desktop**, plus
wired **headphones**.

Please don't substitute another browser, even a Chromium-based one:

- **Brave** blocks parts of the camera API by default (Shields), so you can join
  the room and appear to be connected while sending no video at all.
- **Safari and Firefox** can't reliably do the local recording this setup relies on.
- **A phone won't work.** Every iOS browser — including "Chrome" — is Safari
  underneath, and the local recording is lost the moment the screen locks or a
  call comes in.

Chirag will send you a link that looks like this:

```
https://vdo.ninja/?room=ROOM&push=YOUR-ID&password=PW&record=6000
```

Don't edit it. The `push=YOUR-ID` part is how the studio finds your camera — if
it changes, you appear as a black box with no error shown.

## Before we start

1. **Headphones.** Not optional. Speakers put my voice back into your mic and
   there's no fixing that afterwards.
2. **Wired ethernet** if you can. Failing that, sit close to the router.
3. **Quit everything else.** Especially anything else using the camera, and
   anything syncing in the background.
4. **Check your disk.** The local recording runs about **45 MB per minute**, so
   a 90-minute episode needs ~4 GB free.

## Recording

When you open the link, allow camera and mic, then confirm you can see yourself.

Your browser records a **full-quality local copy** to your Downloads folder at
the same time as it streams to me. The stream is compressed to survive the
network; the local file isn't. That local file is what actually gets used, so
the episode's quality doesn't depend on your connection holding up.

Two things that will cost us the recording if you get them wrong:

- **Stop the recording before you hang up**, using the button on the page.
- **Don't force-quit the browser** while it's recording. The file is still
  being written and won't be readable.

At the very start I'll ask you to **clap once**. That's the sync point for
lining your local file up with mine in the edit — please don't skip it.

## Sharing your screen

Press the screen-share button on the VDO.Ninja page. Share **one window**, not
your whole desktop — notifications, tabs and your dock all end up on camera
otherwise.

Your screen arrives as a separate feed from your camera, so I can put your face
and your screen side by side rather than having to choose. Nothing extra for
you to do; just start the share and I'll switch to it.

## Afterwards

Send me the file from your Downloads folder. It'll be a `.webm`. If it's too
big to email, any file-transfer link is fine.

## If something goes wrong mid-recording

Reload the page. You'll reconnect to the same room automatically and I'll still
have everything up to that point — **but reloading starts a new local recording
file**, so send me *all* of them, not just the last one.
