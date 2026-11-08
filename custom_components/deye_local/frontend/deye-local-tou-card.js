// The integration's one dashboard resource: it loads both cards. Each file is
// loaded with this file's version query so an update never pairs it with a
// cached old copy.
const version = new URL(import.meta.url).search;
const [{ defineTouCard }] = await Promise.all([
  import(`./tou-card-core.js${version}`),
  import(`./deye-local-battery-card.js${version}`),
]);

defineTouCard({
  domain: "deye_local",
  type: "deye-local-tou-card",
  name: "Deye Local Time Of Use",
  description: "The inverter's Time Of Use table, edited as on its screen and saved in one write.",
  documentationURL: "https://github.com/maxbanton/hass-deye-local#time-of-use-card",
  readSchedule: (slots) => slots,
  pendingMs: 30000,
});
