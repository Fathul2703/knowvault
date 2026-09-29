"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap, type User } from "@/lib/api/client";

export const currentUserKey = ["auth", "me"] as const;

export function useCurrentUser() {
  return useQuery<User, ApiError>({
    queryKey: currentUserKey,
    queryFn: () => unwrap(api.GET("/api/v1/auth/me")),
    retry: (count, error) => error.status >= 500 && count < 2,
  });
}

export type LoginInput = { email: string; password: string };

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation<User, ApiError, LoginInput>({
    mutationFn: (body) => unwrap(api.POST("/api/v1/auth/login", { body })),
    onSuccess: (user) => queryClient.setQueryData(currentUserKey, user),
  });
}

export type RegisterInput = LoginInput & { display_name: string; invite_code: string };

export function useRegister() {
  const queryClient = useQueryClient();
  return useMutation<User, ApiError, RegisterInput>({
    mutationFn: (body) => unwrap(api.POST("/api/v1/auth/register", { body })),
    onSuccess: (user) => queryClient.setQueryData(currentUserKey, user),
  });
}

/**
 * Revokes the session. Callers should follow up with a full page navigation
 * (`window.location.assign`), which also discards every cached query of the old session.
 */
export function useLogout() {
  return useMutation<void, ApiError>({
    mutationFn: () => unwrap(api.POST("/api/v1/auth/logout")),
  });
}
