import { useEffect, useState } from "react";

import { useAuth } from "../context/AuthContext.jsx";
import { label } from "../i18n/translate.js";
import { api } from "../services/api.js";

export function useProductCatalog() {
  const { session } = useAuth();
  const token = session?.access_token;
  const [products, setProducts] = useState([]);
  const [productError, setProductError] = useState("");
  const [productsLoading, setProductsLoading] = useState(Boolean(token));

  useEffect(() => {
    if (!token) return undefined;
    let active = true;
    setProductsLoading(true);
    setProductError("");
    api
      .listProducts(token)
      .then((items) => active && setProducts(items))
      .catch((error) => active && setProductError(error.message || label("catalog.loadFailed")))
      .finally(() => active && setProductsLoading(false));
    return () => {
      active = false;
    };
  }, [token]);

  return { products, productError, productsLoading };
}
