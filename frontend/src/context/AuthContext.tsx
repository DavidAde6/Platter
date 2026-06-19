import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  clearAuth,
  fetchCurrentUser,
  getStoredToken,
  getStoredUser,
  login as loginRequest,
  signup as signupRequest,
  storeAuth,
  updateCurrentUser,
  type User,
} from "../lib/auth";

interface AuthContextValue {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (
    name: string,
    email: string,
    password: string,
    dailyCaloricTarget?: number | null,
  ) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
  updateProfile: (payload: {
    user_name?: string;
    daily_caloric_target?: number | null;
    password?: string;
  }) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => getStoredUser());
  const [token, setToken] = useState<string | null>(() => getStoredToken());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const storedToken = getStoredToken();
    if (!storedToken) {
      setLoading(false);
      return;
    }

    fetchCurrentUser(storedToken)
      .then((currentUser) => {
        setUser(currentUser);
        setToken(storedToken);
        storeAuth(storedToken, currentUser);
      })
      .catch(() => {
        clearAuth();
        setUser(null);
        setToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const response = await loginRequest({ user_email: email, password });
    storeAuth(response.access_token, response.user);
    setToken(response.access_token);
    setUser(response.user);
  }, []);

  const signup = useCallback(
    async (
      name: string,
      email: string,
      password: string,
      dailyCaloricTarget?: number | null,
    ) => {
      const response = await signupRequest({
        user_name: name,
        user_email: email,
        password,
        daily_caloric_target: dailyCaloricTarget ?? null,
      });
      storeAuth(response.access_token, response.user);
      setToken(response.access_token);
      setUser(response.user);
    },
    [],
  );

  const logout = useCallback(() => {
    clearAuth();
    setToken(null);
    setUser(null);
  }, []);

  const refreshUser = useCallback(async () => {
    const activeToken = getStoredToken();
    if (!activeToken) return;

    const currentUser = await fetchCurrentUser(activeToken);
    storeAuth(activeToken, currentUser);
    setUser(currentUser);
  }, []);

  const updateProfile = useCallback(
    async (payload: {
      user_name?: string;
      daily_caloric_target?: number | null;
      password?: string;
    }) => {
      const activeToken = getStoredToken();
      if (!activeToken) {
        throw new Error("Not authenticated");
      }

      const updatedUser = await updateCurrentUser(activeToken, payload);
      storeAuth(activeToken, updatedUser);
      setUser(updatedUser);
    },
    [],
  );

  const value = useMemo(
    () => ({
      user,
      token,
      loading,
      login,
      signup,
      logout,
      refreshUser,
      updateProfile,
    }),
    [user, token, loading, login, signup, logout, refreshUser, updateProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
