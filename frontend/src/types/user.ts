export interface User {
  is_demo?: boolean;
  demo_expires_at?: string | null;
  id: string;
  username: string;
  full_name: string;
  email: string;
  gender: string | null;
  birth: string | null;
  height_cm: number | null;
  address: string | null;
  social_media: Record<string, unknown> | null;
  shoe_size: string | null;
  interests: string[] | null;
  created_at: string;
  updated_at: string;
}

export interface UserUpdate {
  full_name?: string;
  gender?: string | null;
  birth?: string | null;
  height_cm?: number | null;
  address?: string | null;
  social_media?: Record<string, unknown> | null;
  shoe_size?: string | null;
  interests?: string[] | null;
}
