export interface Marketplace {
  id: number;
  code: string;
  name: string;
  domain: string;
  default_tag: string;
}

export interface TrackingID {
  id: number;
  marketplace_id: number;
  tag: string;
  marketplace: Marketplace;
}

export interface User {
  id: number;
  name: string;
  whatsapp_number: string;
  email: string | null;
  link_preference: "direct" | "hub";
  store_name: string;
  tracking_ids: TrackingID[];
}

export interface Replacement {
  original: string;
  rewritten: string;
  marketplace_code: string;
}

export interface SkippedLink {
  url: string;
  reason: string;
}

export interface ProcessResponse {
  text: string;
  links_replaced: number;
  replacements: Replacement[];
  skipped: SkippedLink[];
}

export interface PortalAdminAccount {
  id: number;
  username: string;
  whatsapp_number: string;
  created_at: string;
  disabled: boolean;
  avatar: string;
  store_slug: string;
  store_enabled: boolean;
  bank: string;
  account_title: string;
  account_number: string;
  links: number;
  views: number;
  clicks: number;
  orders: number;
  shipped_orders: number;
  name: string;
  link_preference: string;
  store_name: string;
  linked_numbers: string[];
  tracking_ids: { marketplace_code: string; marketplace_name: string; tag: string }[];
}

export interface PortalAdminData {
  accounts: PortalAdminAccount[];
  not_signed_up: { id: number; name: string; whatsapp_number: string }[];
}

export interface PortalAdminLink {
  id: string;
  marketplace: string;
  title: string;
  views: number;
  clicks: number;
  created_at: string;
  article_url: string;
}

export interface PerfUser {
  username: string;
  whatsapp_number: string;
  name: string;
  views: number;
  clicks: number;
  links: number;
}

export interface PerformanceData {
  per_user: PerfUser[];
  series: { date: string; views: number; clicks: number }[];
}

export interface EarningsUserRow {
  account_id: number;
  username: string;
  whatsapp_number: string;
  name: string;
  rate: number;
  custom_rate: number | null;
  earned: number;
  paid: number;
  balance: number;
  entries_count: number;
}

export interface EarningsOverview {
  settings: { default_rate: number; min_payout: number };
  users: EarningsUserRow[];
  /* All-time across every user, deliberately not affected by any date filter:
     what is owed right now, and what has been sent in total. */
  totals: {
    to_be_paid: number;
    paid: number;
    overdrawn_users: number;
  };
}

export interface EarningsEntryOut {
  id: number;
  kind: string;
  gross_amount: number;
  rate_applied: number;
  net_amount: number;
  /* Units returned — only meaningful on a 'return' entry. */
  orders_count: number;
  label: string;
  note: string;
  created_at: string;
}

export interface PayoutOut {
  id: number;
  amount: number;
  /* Orders this payout settled; subtracted from the user's order counts. */
  orders_paid: number;
  method: string;
  note: string;
  paid_at: string;
}

export interface EarningsDetailData {
  username: string;
  rate: number;
  custom_rate: number | null;
  payout_method: string;
  /* Lifetime figures — admin-only. The user is shown current figures only. */
  earned: number;
  paid: number;
  /* The user's "Current total earnings". */
  balance: number;
  entries_count: number;
  return_orders: number;
  returned_amount: number;
  orders_paid: number;
  /* Derived: what the admin entered, minus what payouts have settled. */
  current_orders: number;
  current_shipped: number;
  /* The untouched running totals the admin typed from Amazon. */
  orders_entered: number;
  shipped_entered: number;
  entries: EarningsEntryOut[];
  payouts: PayoutOut[];
  referrals: ReferralOut[];
}

export interface ReferralOut {
  id: number;
  referred_name: string;
  amount: number;
  note: string;
  created_at: string;
}

/* Credentials for the Portal administration -> Logins tab. `password` is empty
   when the user has since set their own — the tab shows that as "changed by
   user" rather than a blank, because a blank reads as "no password". */
export interface LoginRow {
  account_id: number;
  username: string;
  whatsapp_number: string;
  name: string;
  password: string;
  /* True when a password IS stored but could not be read — i.e. the key was
     rotated. Distinct from nothing stored, which means the user changed it. */
  has_stored: boolean;
  disabled: boolean;
  created_at: string;
}

export interface LoginsData {
  storage_enabled: boolean;
  accounts: LoginRow[];
}
