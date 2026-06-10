# Stack-chan Rollout

Do not run this rollout until the final wake stability test is complete.

## Pre-deploy

1. Confirm the wake run finished and `send_note` delivery was observed.
2. Save the current Render deploy commit.
3. Review `schema/stackchan_queue.sql`.
4. Generate one long random `STACKCHAN_DEVICE_TOKEN`.

## Deploy

1. Apply `schema/stackchan_queue.sql` in Supabase.
2. Set these Render variables:
   - `STACKCHAN_DEVICE_TOKEN`
   - `STACKCHAN_SPEAK_TTL_SECONDS=30`
   - `STACKCHAN_WIGGLE_TTL_SECONDS=10`
3. Push the reviewed commit and deploy it to Render.
4. Verify `/health`.
5. Run the existing MCP smoke test, requiring at least:
   - `system_status`
   - `send_note`
   - `toy_safety_status`
   - `stackchan_status`
   - `stackchan_speak`
6. Run the Stack-chan simulator against Render.
7. Queue two speech commands and confirm FIFO execution.
8. Queue two expressions and confirm only the newest pending expression runs.
9. Queue repeated wiggles and confirm they collapse and expire when unclaimed.
10. Refresh the Claude connector tool list only after all server checks pass.

## Rollback

1. Roll Render back to the saved pre-deploy commit.
2. Do not drop the added Supabase columns during an incident; they are backward
   compatible with the previous service.
3. Revoke or rotate `STACKCHAN_DEVICE_TOKEN` if device authentication is in
   doubt.
4. Confirm `send_note` and `toy_safety_status` with the existing smoke test.
