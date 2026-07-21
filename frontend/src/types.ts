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
  name: string;
  link_preference: string;
  store_name: string;
  linked_numbers: string[];
}

export interface PortalAdminData {
  accounts: PortalAdminAccount[];
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
}

export interface EarningsEntryOut {
  id: number;
  kind: string;
  gross_amount: number;
  rate_applied: number;
  net_amount: number;
  label: string;
  note: string;
  created_at: string;
}

export interface PayoutOut {
  id: number;
  amount: number;
  method: string;
  note: string;
  paid_at: string;
}

export interface EarningsDetailData {
  username: string;
  rate: number;
  custom_rate: number | null;
  payout_method: string;
  earned: number;
  paid: number;
  balance: number;
  entries_count: number;
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
