export function getApiErrorMessage(error: unknown, fallback: string): string {
  const axiosError = error as {
    response?: {
      data?: {
        error?: {
          message?: string;
        };
      };
    };
  };
  return axiosError.response?.data?.error?.message || fallback;
}
