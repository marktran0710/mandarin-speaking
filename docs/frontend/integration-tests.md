# Frontend integration tests

The integration suite exercises the main React flows with deterministic test doubles at the network/database boundary:

- student login and independent role sessions;
- learner workspace quiz gate and activity start callback;
- teacher sign-in and class overview;
- admin account create, edit, and delete flows.

From the `frontend` folder:

```powershell
npm run test:integration
```

The suite does not modify the real database or require the backend to be running. It complements the existing unit/component suite; browser smoke testing against Docker remains a separate deployment check.
