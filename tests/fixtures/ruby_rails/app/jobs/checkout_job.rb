require "net/http"

module Jobs
  class CheckoutJob
    def self.call(order)
      NotifyUser.call(order)

      if order.urgent?
        NotifyUser.call(order)
      elsif order.preview?
        Audit.log(order)
      else
        ArchiveOrder.call(order)
      end

      puts "if this string should not count"
    end
  end
end
