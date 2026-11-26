package users

import (
    "encoding/json"
    "flag"
    "testing"
)

func TestNativeHrefJSONContract(t *testing.T) {
    flag.Set("link-domain", "user")
    user := User{UserID: "probe"}
    user.AddLinks()
    body, err := json.Marshal(user)
    if err != nil { t.Fatal(err) }
    var decoded struct {
        Links map[string]struct{ Href string `json:"href"` } `json:"_links"`
    }
    if err := json.Unmarshal(body, &decoded); err != nil { t.Fatal(err) }
    for key, suffix := range map[string]string{
        "self":"", "customer":"", "addresses":"/addresses", "cards":"/cards",
    } {
        if decoded.Links[key].Href != "http://user/customers/probe"+suffix {
            t.Errorf("%s link did not preserve the API contract: %s", key, string(body))
        }
    }
}
