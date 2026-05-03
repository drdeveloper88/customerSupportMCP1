/**
 * useApi.js
 * Generic async data-fetching hook.
 *
 * Usage:
 *   const { data, loading, error, refetch } = useApi(() => fetchOrders(customerId), [customerId])
 *
 * @template T
 * @param {() => Promise<T>} asyncFn  - The async function to call
 * @param {Array}            deps     - Dependency array (re-runs when changed)
 * @returns {{ data: T|null, loading: boolean, error: string|null, refetch: function }}
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export function useApi(asyncFn, deps = []) {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  // Keep a stable reference to the function
  const fnRef = useRef(asyncFn)
  useEffect(() => { fnRef.current = asyncFn })

  const execute = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fnRef.current()
      setData(result)
    } catch (err) {
      setError(err?.message ?? 'Unknown error')
    } finally {
      setLoading(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => { execute() }, [execute])

  return { data, loading, error, refetch: execute }
}
