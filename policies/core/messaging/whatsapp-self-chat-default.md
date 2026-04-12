# WhatsApp: self-chat default on Hermes gateways

## Scope

Hermes deployments that use the built-in **Baileys** WhatsApp bridge (`scripts/whatsapp-bridge/bridge.js`).

## Policy

1. **Preferred production pattern (two isolated hosts, two numbers):** **`WHATSAPP_MODE=self-chat`** on **each** gateway. The operator uses the **personal** WhatsApp login; the droplet uses the **business** (or other dedicated) login. The human interacts with Hermes only in the **self-chat** thread on **that** number.

2. **Do not** rely on the deprecated pattern where the operator runs **`WHATSAPP_MODE=bot`** and **`WHATSAPP_ALLOWED_USERS`** lists the **other** line’s number so traffic flows via personal↔business DMs. That cross-number bridge is **not** the default and must not be documented as the recommended two-host path.

3. **Inbound scope:** With **`WHATSAPP_MODE=self-chat`** and **`WHATSAPP_ALLOW_NON_SELF_DM`** unset or false, the bridge **does not** deliver **groups**, **status**, or **non-self** 1:1 chats to the gateway. Outbound from Hermes should match the same intent (self-chat thread only) unless configuration is deliberately widened.

4. **Strangers / allowlist:** The gateway defaults **`get_unauthorized_dm_behavior`** to **`ignore`** for WhatsApp when not overridden in config, so numbers **not** on **`WHATSAPP_ALLOWED_USERS`** do **not** receive Hermes or pairing replies. Native WhatsApp delivery to the owner’s phone is unchanged.

4. **Widening access:** Additional numbers, groups, or non-self DMs require an explicit operator decision: set **`WHATSAPP_ALLOW_NON_SELF_DM=true`** and adjust **`WHATSAPP_ALLOWED_USERS`** / **`WHATSAPP_ALLOWED_CHATS`** as documented in the user guide.

## References

- `website/docs/user-guide/messaging/two-host-operator-droplet.md`
- `website/docs/user-guide/messaging/whatsapp.md`
